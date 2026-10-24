"use client";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "./ui/notchset/select";

export type Choice = { value: string; label: string; disabled?: boolean };
/** Form-compatible select; no fetching or permission decisions. */
export function ChoiceSelect({
  id,
  name,
  label,
  value,
  defaultValue,
  onValueChange,
  options,
  disabled,
}: {
  id?: string;
  name?: string;
  label: string;
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  options: readonly Choice[];
  disabled?: boolean;
}) {
  return (
    <Select
      name={name}
      value={value}
      defaultValue={defaultValue}
      disabled={disabled}
      items={options}
      onValueChange={(next) => {
        if (next !== null) onValueChange?.(next);
      }}
    >
      <SelectTrigger id={id} aria-label={label}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem
            key={option.value}
            value={option.value}
            disabled={option.disabled}
          >
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
