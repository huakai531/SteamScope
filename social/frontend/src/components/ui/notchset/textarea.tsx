/** Textarea (Notchset) v1.0.0 · Beautiful UI · MIT.
 * https://beautiful-ui.dev/components/textarea — no AI token/cost-meter variants. */
import type * as React from "react";
import { cn } from "@/lib/utils";
import { textareaClass } from "@/lib/beautiful-ui/notchset/field-classes";
import { NOTCHSET_ROOT } from "@/lib/beautiful-ui/notchset/root";

/* SteamScope uses the primitive only; no AI field/token-meter variants. */

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      {...NOTCHSET_ROOT}
      data-slot="textarea"
      className={cn(textareaClass, className)}
      {...props}
    />
  );
}

export { Textarea };
