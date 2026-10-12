"""Offline checks of cross-project submission isolation and grading semantics."""
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import workflow
from runtime import LOCAL


class WorkflowTests(unittest.TestCase):
    def test_component_patch_applies_to_original_layout_and_omits_other_projects(self):
        with tempfile.TemporaryDirectory(dir=LOCAL) as tmp:
            root = Path(tmp); repo=root/'repo'; repo.mkdir()
            def git(*args):
                return subprocess.run(['git','-C',str(repo),*args],check=True,capture_output=True,text=True)
            git('init','-q');git('config','user.name','Eval');git('config','user.email','eval@localhost')
            for name in ['fixture-a','fixture-b']:
                dest=repo/'parts'/name;dest.mkdir(parents=True);(dest/'file.txt').write_text('original\n')
            git('add','.');git('commit','-qm','base');base=git('rev-parse','HEAD').stdout.strip()
            (repo/'parts/fixture-a/file.txt').write_text('changed\n')
            (repo/'parts/fixture-a/new.txt').write_text('new source\n')
            (repo/'parts/fixture-b/file.txt').write_text('other project\n')
            git('add','.');git('commit','-qm','implementation')
            (repo/'parts/fixture-a/file.txt').write_text('uncommitted change\n')
            auth=root/'auth.json';auth.write_text(json.dumps({'tokens':{}}))
            rt=SimpleNamespace(root=root/'run',name='test-runtime',auth=auth)
            def fake_docker(*args):
                marker=args.index('git');command=list(args[marker:]);command[command.index('/app')]=str(repo)
                return subprocess.run(command,check=True,capture_output=True,text=True)
            with patch.object(workflow,'checked_component',return_value='fixture-a'),patch.object(workflow,'docker',side_effect=fake_docker):
                artifact=workflow.component_patch(rt,base,{'id':'fixture-a'})
            content=artifact.read_text()
            self.assertIn('diff --git a/file.txt b/file.txt',content)
            self.assertNotIn('fixture-b',content);self.assertNotIn('parts/fixture-a',content)
            self.assertNotIn('uncommitted change',content)
            pristine=root/'pristine';pristine.mkdir();(pristine/'file.txt').write_text('original\n')
            subprocess.run(['git','-C',str(pristine),'init','-q'],check=True)
            subprocess.run(['git','-C',str(pristine),'apply',str(artifact)],check=True)
            self.assertEqual((pristine/'file.txt').read_text(),'changed\n')
            self.assertEqual((pristine/'new.txt').read_text(),'new source\n')

    def test_workflow_score_retains_component_failure(self):
        with tempfile.TemporaryDirectory(dir=LOCAL) as tmp:
            root=Path(tmp);artifact=root/'submission.patch';artifact.write_text('fixture')
            rt=SimpleNamespace(root=root,name='test-runtime')
            meta={'metadata':{'base_commit_hash':'a'*40},'workflow_components':[
                {'id':name,'source_path':str(root),'image':{'image':'fixture'}} for name in ['one','two']]}
            grades=[dict(status='graded',success=True,details={'f2p_total':4,'f2p_passed':4}),
                    dict(status='graded',success=False,details={'f2p_total':4,'f2p_passed':3})]
            with patch.object(workflow,'component_patch',return_value=artifact),patch('run_stage.grade_deep',side_effect=grades):
                result=workflow.grade_workflow(rt,meta)
            self.assertFalse(result['success']);self.assertEqual(result['reward'],0)
            self.assertEqual(result['details']['component_fraction'],.5)
            self.assertEqual(result['details']['f2p'],7/8)
            self.assertEqual(len(result['components']),2)


if __name__ == '__main__':unittest.main()
