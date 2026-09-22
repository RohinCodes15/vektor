"use client";

import { motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";

export function Reveal({ children }: { children: ReactNode }) {
  const reduced = useReducedMotion();
  return <motion.div initial={false} animate={{ y: reduced ? 0 : [4, 0] }} className="workspace">{children}</motion.div>;
}
