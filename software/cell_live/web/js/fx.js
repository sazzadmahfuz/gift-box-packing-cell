// Motion helpers. Rule: motion only follows a real event (a check finished, a state changed, a number
// arrived). Nothing here plays on a timer of its own, and everything is skipped when the person has
// asked their system for less motion.

export const calm = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// Play a CSS animation class again: remove it, force a reflow, add it.
export function replay(node, className) {
  if (!node || calm()) return;
  node.classList.remove(className);
  void node.getBoundingClientRect();
  node.classList.add(className);
}

// Fill a .spark node with small bars from real numbers (the latest value is highlighted by the CSS).
export function sparkInto(node, values) {
  const top = Math.max(...values, 1);
  node.replaceChildren(...values.map((value) => {
    const bar = document.createElement("i");
    bar.style.setProperty("--v", String(Math.max(8, Math.round((value / top) * 100))));
    return bar;
  }));
}
