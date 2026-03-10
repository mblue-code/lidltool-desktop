import { useEffect, useRef, useState } from "react";
import { Loader2, Search, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

type SearchInputProps = {
  placeholder?: string;
  value: string;
  onChange: (value: string) => void;
  debounceMs?: number;
  isLoading?: boolean;
  className?: string;
};

export function SearchInput({
  placeholder,
  value,
  onChange,
  debounceMs = 300,
  isLoading,
  className
}: SearchInputProps) {
  const [localValue, setLocalValue] = useState(value);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    setLocalValue(value);
  }, [value]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      onChangeRef.current(localValue);
    }, debounceMs);
    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [localValue, debounceMs]);

  return (
    <div className={cn("relative", className)}>
      <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <Input
        value={localValue}
        onChange={(event) => setLocalValue(event.target.value)}
        placeholder={placeholder}
        className="pl-8 pr-8"
      />
      {isLoading ? (
        <Loader2 className="absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-muted-foreground" />
      ) : localValue ? (
        <button
          type="button"
          onClick={() => {
            setLocalValue("");
            onChangeRef.current("");
          }}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </button>
      ) : null}
    </div>
  );
}
