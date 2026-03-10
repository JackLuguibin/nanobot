/**
 * 将 token 计数格式化为 K、M、G 等单位
 * 例如: 64134 -> "64.1K", 1234567 -> "1.2M"
 */
export function formatTokenCount(n: number): string {
  if (typeof n !== 'number' || !Number.isFinite(n)) return '-';
  if (n < 0) return '-';
  if (n < 1000) return String(n);
  if (n < 1_000_000) return `${(n / 1000).toFixed(1).replace(/\.0$/, '')}K`;
  if (n < 1_000_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`;
  return `${(n / 1_000_000_000).toFixed(1).replace(/\.0$/, '')}G`;
}
