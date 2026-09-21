"use client";

import { MotionConfig, motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";

export function Reveal({ children }: { children: ReactNode }) {
  const reduced = useReducedMotion();
  return <MotionConfig reducedMotion="user"><motion.div initial={{ y: 6 }} animate={{ y: 0 }} transition={{ duration: reduced ? 0 : 0.25 }} className="workspace">{children}</motion.div></MotionConfig>;
}
