export function getDateString(date: Date | string) {
    return date instanceof Date ? date.toLocaleDateString() : new Date(date).toLocaleDateString();
}