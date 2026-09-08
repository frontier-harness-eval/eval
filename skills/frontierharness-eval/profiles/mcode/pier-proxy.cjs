// Keep both of MCode's HTTP clients on Pier's native authenticated proxy.
const { EnvHttpProxyAgent, setGlobalDispatcher } = require('./pier-network/package');
if (!process.env.HTTPS_PROXY) throw new Error('Pier agent proxy is missing');
setGlobalDispatcher(new EnvHttpProxyAgent());
