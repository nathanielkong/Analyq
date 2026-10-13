// Older saved reports may still contain provider subscription advertisements.
export function providerNotice(message: string): string {
  if (/premium|alphavantage\.co\/premium/i.test(message)) {
    return 'Some data is not available on the current provider plan.'
  }
  if (/rate limit|call frequency|requests per day/i.test(message)) {
    return 'Some data is temporarily unavailable because the provider request limit was reached.'
  }
  return message
}
