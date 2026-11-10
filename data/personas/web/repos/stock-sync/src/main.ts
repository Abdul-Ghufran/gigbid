import redis
import psycopg

// stock-sync: core module
export async function run(config: Record<string, string>) {
  const data = await load(config);
  return process(data);
}
