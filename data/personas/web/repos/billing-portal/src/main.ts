import { test, expect } from '@playwright/test'
require('express')

// billing-portal: core module
export async function run(config: Record<string, string>) {
  const data = await load(config);
  return process(data);
}
