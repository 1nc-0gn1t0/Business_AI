import body from "./assets/vi/motion/body.webp?no-inline";
import hand from "./assets/vi/motion/hand.webp?no-inline";
import plume1 from "./assets/vi/motion/plume1.webp?no-inline";
import plume2 from "./assets/vi/motion/plume2.webp?no-inline";
import plume3 from "./assets/vi/motion/plume3.webp?no-inline";
import eye_left from "./assets/vi/motion/eye_left.webp?no-inline";
import eye_right from "./assets/vi/motion/eye_right.webp?no-inline";
import rig from "./assets/vi/motion/provenance.json";

export type ViMotion =
  | "idle"
  | "greeting"
  | "thinking"
  | "searching"
  | "idea"
  | "success"
  | "error"
  | "none";
const layers = { body, hand, plume1, plume2, plume3, eye_left, eye_right };
export function ViRig({
  size,
  portrait,
  motion,
}: {
  size: number;
  portrait: boolean;
  motion: ViMotion;
}) {
  function layer(name: keyof typeof layers) {
    const [x, y, right, bottom] = rig.layers[name].bounds;
    return (
      <g className={`vi-rig-${name}`}>
        <image
          href={layers[name]}
          x={x}
          y={y}
          width={right - x}
          height={bottom - y}
        />
      </g>
    );
  }
  return (
    <svg
      className={`vi-avatar vi-rig vi-motion-${motion} ${portrait ? "vi-portrait" : ""}`}
      data-motion={motion}
      data-rig="layered"
      viewBox={portrait ? "100 0 620 590" : "0 0 740 785"}
      width={size}
      height={size}
      aria-hidden="true"
      focusable="false"
    >
      <g className="vi-rig-character">
        {layer("plume1")}
        {layer("plume2")}
        {layer("plume3")}
        {layer("body")}
        {layer("hand")}
        {layer("eye_left")}
        {layer("eye_right")}
      </g>
    </svg>
  );
}
