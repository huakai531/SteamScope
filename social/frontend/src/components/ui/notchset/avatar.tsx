"use client";
/**
 * Avatar (Notchset) v1.0.0 · Beautiful UI · MIT
 * Source: https://beautiful-ui.dev/components/avatar
 * Installed with shadcn 4.21.0; adapted to SteamScope's existing visual system.
 * Unused demo, sound and instrument variants removed. Accessible primitives retained.
 */
import * as React from "react";
import Image from "next/image";
import { cn } from "@/lib/utils";
import { NOTCHSET_ROOT } from "@/lib/beautiful-ui/notchset/root";

export const initials = (name: string) =>
  name
    .trim()
    .split(/\s+/)
    .map((word) => Array.from(word)[0]?.toUpperCase())
    .slice(0, 2)
    .join("") || "S";
export function Avatar({
  name,
  src,
  size = "m",
  className,
  ...props
}: React.ComponentProps<"span"> & {
  name: string;
  src?: string;
  size?: "s" | "m" | "l";
}) {
  // Image status belongs to this source; changing a failed source tries the new one.
  const [image, setImage] = React.useState<{
    src: string;
    state: "loaded" | "failed";
  } | null>(null);
  const loaded = image?.src === src && image?.state === "loaded";
  const failed = image?.src === src && image?.state === "failed";
  return (
    <span
      {...NOTCHSET_ROOT}
      role="img"
      aria-label={name}
      data-slot="avatar"
      data-size={size}
      className={cn("bui-avatar", className)}
      {...props}
    >
      <span
        aria-hidden="true"
        data-slot="avatar-fallback"
        style={{ opacity: loaded ? 0 : 1 }}
      >
        {initials(name)}
      </span>
      {src && !failed && (
        <Image
          alt=""
          src={src}
          width={80}
          height={80}
          unoptimized
          loading="lazy"
          decoding="async"
          referrerPolicy="no-referrer"
          data-slot="avatar-image"
          onLoad={() => setImage({ src, state: "loaded" })}
          onError={() => setImage({ src, state: "failed" })}
          style={{ opacity: loaded ? 1 : 0 }}
        />
      )}
    </span>
  );
}
