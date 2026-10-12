import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from runtime import Runtime

class SubscriptionAdmissionTests(unittest.TestCase):
    def test_api_key_and_non_subscription_auth_fail_before_container_launch(self):
        cases=[{'auth_mode':'apikey','OPENAI_API_KEY':'test-fixture'},
               {'auth_mode':'chatgpt','OPENAI_API_KEY':'test-fixture','tokens':{'access_token':'test-fixture'}},
               {'auth_mode':'chatgpt','tokens':{}}]
        for case in cases:
            with self.subTest(case=case),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);auth=root/'approved-auth.json';auth.write_text(json.dumps(case))
                with patch('runtime.LOCAL',root),patch('runtime.docker') as launch:
                    task=Runtime('no-paid-admission','fixture',{},auth=auth)
                    with self.assertRaisesRegex(RuntimeError,'Subscription-only'):
                        task.start()
                    launch.assert_not_called()

if __name__=='__main__':unittest.main()
