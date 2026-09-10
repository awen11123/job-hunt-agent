import { describe, expect, it } from "vitest";

import { compareInstantsDescending, localDateFromInstant } from "./localDate";

describe("local date helpers", () => {
  it("converts a UTC instant across midnight in the requested time zone", () => {
    expect(
      localDateFromInstant("2026-09-10T16:30:00Z", "Asia/Shanghai"),
    ).toBe("2026-09-11");
  });

  it("sorts equivalent ISO offsets by their actual instant", () => {
    const earlier = "2026-09-11T00:15:00+08:00";
    const later = "2026-09-10T16:45:00Z";

    expect(compareInstantsDescending(later, earlier)).toBeLessThan(0);
  });
});
