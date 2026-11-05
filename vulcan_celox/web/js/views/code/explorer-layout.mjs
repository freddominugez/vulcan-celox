// The bar between the tree and the viewer: drag or arrow keys, between 180 px and half of the area.

export const MIN_WIDTH = 180;

export function bindResize(handle, area, side, remember) {
  const set = (px) => {
    const max = Math.max(MIN_WIDTH, area.clientWidth * 0.5);
    const width = Math.round(Math.min(max, Math.max(MIN_WIDTH, px)));
    area.style.setProperty("--ce-tree", `${width}px`);
    remember(width);
  };
  handle.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    handle.setPointerCapture(e.pointerId);
    const left = area.getBoundingClientRect().left;
    const move = (ev) => set(ev.clientX - left);
    const up = () => {
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", up);
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", up);
  });
  handle.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    set(side.getBoundingClientRect().width + (e.key === "ArrowLeft" ? -24 : 24));
  });
}
