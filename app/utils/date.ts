export function getDateString(date: Date | string) {
    return date instanceof Date ? date.toLocaleDateString() : new Date(date).toLocaleDateString();
}

export function getShortDateString(date: Date | string) {
    const d = date instanceof Date ? date : new Date(date);
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function getISOString(date: Date | string) {
    const d = date instanceof Date ? date : new Date(date);
    return d.toISOString();
}