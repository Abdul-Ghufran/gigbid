@tailwind base

// menu-pwa: core module
export async function run(config: Record<string, string>) {
  const data = await load(config);
  return process(data);
}
