/** Input (Notchset) v1.0.0 · Beautiful UI · MIT.
 * https://beautiful-ui.dev/components/input — SteamScope primitive-only adaptation. */
import type * as React from "react";
import { Input as InputPrimitive } from "@base-ui/react/input";
import { cn } from "@/lib/utils";
import { inputClass } from "@/lib/beautiful-ui/notchset/field-classes";
import { NOTCHSET_ROOT } from "@/lib/beautiful-ui/notchset/root";

/* SteamScope uses the primitive only; no AI field/token-meter variants. */

function Input({ className, type, ...props }: InputPrimitive.Props) {
  return (
    <InputPrimitive
      {...NOTCHSET_ROOT}
      type={type}
      data-slot="input"
      // A string unless you pass a function: functions can't cross into this client primitive from a Server Component.
      className={
        typeof className === "function"
          ? (state) => cn(inputClass, className(state))
          : cn(inputClass, className)
      }
      {...props}
    />
  );
}

export { Input };
export type InputProps = React.ComponentProps<typeof Input>;
