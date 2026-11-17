/** "1 night", "2 nights"; pass `many` for irregular plurals ("person", "people"). */
export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
