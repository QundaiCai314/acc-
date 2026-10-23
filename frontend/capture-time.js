// A date without a timezone spans every civil offset, not an invented midnight.
export function captureWithinWindow(image, asOf, hours) {
  if (!image) return false;
  const end = new Date(asOf).getTime(), cutoff = end - hours * 3600000;
  const day = Date.parse(image.captured_on + 'T00:00:00Z');
  const earliest = image.captured_at ? Date.parse(image.captured_at) : day - 14 * 3600000;
  const latest = image.captured_at ? earliest : day + 36 * 3600000;
  return earliest >= cutoff && latest <= end;
}
