export const DEFAULT_TIME_ZONE = 'Europe/Brussels';
const TIME_ZONE_KEY = 'omnivision.timeZone';

// ponytail: Intl list is ~400 zones; fine for a single select, no tz library needed
export const TIME_ZONES: string[] = (Intl as any).supportedValuesOf
  ? (Intl as any).supportedValuesOf('timeZone')
  : [DEFAULT_TIME_ZONE, 'UTC'];

export function readTimeZone(): string {
  try {
    return localStorage.getItem(TIME_ZONE_KEY) || DEFAULT_TIME_ZONE;
  } catch {
    return DEFAULT_TIME_ZONE;
  }
}

export function saveTimeZone(timeZone: string): void {
  try {
    localStorage.setItem(TIME_ZONE_KEY, timeZone);
  } catch {
    // storage blocked (private window): the choice just lasts for this visit
  }
}

/** Kickoff in the chosen zone, e.g. "Sat, 10 Oct, 13:30 CEST"; null when there is no usable start time. */
export function formatKickoff(iso: string | undefined, timeZone: string): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return null;
  return new Intl.DateTimeFormat('en-GB', {
    timeZone,
    weekday: 'short',
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
    timeZoneName: 'short',
  }).format(d);
}

/** True once the kickoff time has passed. Matches without a start time are kept. */
export function hasStarted(iso: string | undefined, now: number): boolean {
  const t = iso ? Date.parse(iso) : NaN;
  return !isNaN(t) && t <= now;
}
