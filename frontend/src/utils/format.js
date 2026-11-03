export const number = (value) => new Intl.NumberFormat().format(Number(value || 0));
export const date = (value, options = { month: "short", day: "numeric", year: "numeric" }) => value ? new Intl.DateTimeFormat(undefined, options).format(new Date(value)) : "—";
export const relative = (value) => {
  if (!value) return "—";
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
  if (seconds < 60) return "Just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} hr ago`;
  return `${Math.floor(seconds / 86400)} d ago`;
};
