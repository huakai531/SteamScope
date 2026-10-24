"use client";
/**
 * Button (Notchset) v1.0.0 · Beautiful UI · MIT
 * Source: https://beautiful-ui.dev/components/button
 * Installed with shadcn 4.21.0; adapted to SteamScope's existing visual system.
 * Unused demo, sound and instrument variants removed. Accessible primitives retained.
 */
import * as React from "react";
import { Button as Primitive } from "@base-ui/react/button";
import { cva } from "class-variance-authority";
import { cn } from "@/lib/utils";
import { NOTCHSET_ROOT } from "@/lib/beautiful-ui/notchset/root";

const buttonVariants = cva("bui-button", {
  variants: {
    variant: {
      default: "bui-button-primary",
      secondary: "bui-button-secondary",
      ghost: "bui-button-ghost",
      destructive: "bui-button-danger",
    },
    size: { default: "", sm: "bui-button-sm", icon: "bui-button-icon" },
  },
  defaultVariants: { variant: "default", size: "default" },
});
export type ButtonProps = Primitive.Props & {
  variant?: "default" | "secondary" | "ghost" | "destructive";
  size?: "default" | "sm" | "icon";
  loading?: boolean;
};
export function Button({
  variant,
  size,
  loading,
  disabled,
  className,
  children,
  ...props
}: ButtonProps) {
  return (
    <Primitive
      {...NOTCHSET_ROOT}
      data-slot="button"
      {...props}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={
        typeof className === "function"
          ? (state) => cn(buttonVariants({ variant, size }), className(state))
          : cn(buttonVariants({ variant, size }), className)
      }
    >
      {children}
    </Primitive>
  );
}
