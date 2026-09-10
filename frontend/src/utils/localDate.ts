function dateFormatter(timeZone?: string): Intl.DateTimeFormat {
  return new Intl.DateTimeFormat("zh-CN", {
    ...(timeZone ? { timeZone } : {}),
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

export function localDateFromInstant(value: string, timeZone?: string): string {
  const instant = new Date(value);
  if (Number.isNaN(instant.getTime())) return value.slice(0, 10);

  const parts = dateFormatter(timeZone).formatToParts(instant);
  const year = parts.find((part) => part.type === "year")?.value;
  const month = parts.find((part) => part.type === "month")?.value;
  const day = parts.find((part) => part.type === "day")?.value;
  return year && month && day ? `${year}-${month}-${day}` : value.slice(0, 10);
}

export function compareInstantsDescending(left: string, right: string): number {
  const leftTime = Date.parse(left);
  const rightTime = Date.parse(right);
  if (Number.isNaN(leftTime) || Number.isNaN(rightTime)) {
    return right.localeCompare(left);
  }
  return rightTime - leftTime;
}
