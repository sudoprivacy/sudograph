// The official typed Read RPC propagates the caller's credential. This process
// accepts no --as identity, service token or arbitrary Call method. Credentials
// arrive through stdin and are never command-line arguments or log output.
import { NexusVfsClient } from '@nexus-ai-fs/vfs-client';

let input = '';
for await (const chunk of process.stdin) input += chunk;
let client;
try {
  const { endpoint, path, credential, tls } = JSON.parse(input);
  client = new NexusVfsClient(endpoint, tls ? { tls } : {});
  const content = await client.read(path, credential);
  process.stdout.write(JSON.stringify({ content: content.toString('base64') }));
} catch {
  process.stdout.write(JSON.stringify({ denied: true }));
  process.exitCode = 1;
} finally {
  client?.close();
}
