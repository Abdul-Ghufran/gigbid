runs-on: ubuntu-latest

// fin-e2e: core module
export async function run(config: Record<string, string>) {
  const data = await load(config);
  return process(data);
}
