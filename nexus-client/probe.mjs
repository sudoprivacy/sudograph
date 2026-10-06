// Acceptance fixture only: all reads/writes target the isolated daemon's dummy
// grant file. Never point this at a shared or production namespace.
import { NexusVfsClient } from '@nexus-ai-fs/vfs-client';
let input = '';
for await (const chunk of process.stdin) input += chunk;
const { endpoint, reader, other } = JSON.parse(input);
const client = new NexusVfsClient(endpoint);
async function canRead(credential) {
  try { await client.read('/operator-grant.json', credential); return true; }
  catch { return false; }
}
try {
  const checks = {
    valid_caller_read: await canRead(reader),
    invalid_caller_denied: !await canRead('sk-invalid'),
    anonymous_denied: !await canRead(''),
    other_zone_denied: !await canRead(other),
  };
  const content = await client.read('/operator-grant.json', reader);
  try {
    await client.write('/operator-grant.json', content, reader);
    checks.read_then_write_denied = false;
  } catch { checks.read_then_write_denied = true; }
  process.stdout.write(JSON.stringify(checks));
} finally { client.close(); }
