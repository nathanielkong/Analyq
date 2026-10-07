const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { test } = require('node:test')
const vm = require('node:vm')
const ts = require('typescript')

const source = fs.readFileSync(path.join(__dirname, '../src/api/client.ts'), 'utf8')
const code = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
}).outputText

async function client(env, status = 200) {
  const requests = []
  const context = vm.createContext({
    fetch: async (url, options) => {
      requests.push({ url, options })
      return {
        ok: status >= 200 && status < 300,
        status,
        json: async () => ({ detail: 'Sign in required' }),
      }
    },
  })
  const module = new vm.SourceTextModule(code, {
    context,
    initializeImportMeta(meta) { meta.env = env },
  })
  await module.link(() => { throw new Error('Unexpected client import') })
  await module.evaluate()
  return { api: module.namespace, requests }
}

test('production defaults to same-origin API for every request method', async () => {
  const { api, requests } = await client({ DEV: false })
  await api.apiGet('/health')
  await api.apiGetOptional('/auth/me')
  await api.apiPost('/auth/login', { username: 'synthetic' })
  await api.apiDelete('/auth/session')
  assert.deepEqual(requests.map(r => r.url), [
    '/api/health', '/api/auth/me', '/api/auth/login', '/api/auth/session',
  ])
  for (const request of requests) assert.equal(request.options.credentials, 'include')
  assert.equal(requests[2].options.method, 'POST')
  assert.equal(requests[3].options.method, 'DELETE')
})

test('development retains the local backend default', async () => {
  const { api, requests } = await client({ DEV: true })
  await api.apiGet('/health')
  assert.equal(requests[0].url, 'http://localhost:8000/health')
})

test('explicit proxy override is trimmed and does not duplicate slashes', async () => {
  const { api, requests } = await client({ DEV: false, VITE_API_BASE_URL: ' /api/ ' })
  await api.apiGet('/health')
  assert.equal(requests[0].url, '/api/health')
})

test('blank production override never falls back to localhost', async () => {
  const { api, requests } = await client({ DEV: false, VITE_API_BASE_URL: ' ' })
  await api.apiGet('/health')
  assert.equal(requests[0].url, '/api/health')
})

test('unauthenticated optional requests and protected errors are preserved', async () => {
  const { api } = await client({ DEV: false }, 401)
  assert.equal(await api.apiGetOptional('/auth/me'), null)
  await assert.rejects(api.apiGet('/chat/sessions'), /Sign in required/)
})

test('Vercel strips the API prefix before forwarding and disables API caching', () => {
  const config = JSON.parse(fs.readFileSync(path.join(__dirname, '../vercel.json'), 'utf8'))
  assert.deepEqual(config.rewrites[0], {
    source: '/api/:path*',
    destination: 'https://analyq-api.onrender.com/:path*',
  })
  const headers = config.headers.find(rule => rule.source === '/api/:path*').headers
  assert(headers.some(h => h.key === 'Cache-Control' && h.value.includes('no-store')))
  assert(headers.some(h => h.key === 'Vercel-CDN-Cache-Control' && h.value === 'no-store'))
})
