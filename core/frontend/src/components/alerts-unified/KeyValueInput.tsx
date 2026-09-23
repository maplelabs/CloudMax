import { useState, useEffect } from "react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { X, Plus } from "lucide-react";

interface KeyValuePair {
  key: string;
  value: string;
}

interface KeyValueInputProps {
  value: Record<string, string>;
  onChange: (value: Record<string, string>) => void;
  placeholder?: { key: string; value: string };
  disabled?: boolean;
}

export function KeyValueInput({ value, onChange, placeholder, disabled }: KeyValueInputProps) {
  const [pairs, setPairs] = useState<KeyValuePair[]>(() => {
    return Object.entries(value).map(([key, val]) => ({ key, value: val }));
  });

  // Sync internal state with prop changes (e.g., when form resets)
  useEffect(() => {
    setPairs(Object.entries(value).map(([key, val]) => ({ key, value: val })));
  }, [value]);

  const handleAddPair = () => {
    const newPairs = [...pairs, { key: "", value: "" }];
    setPairs(newPairs);
  };

  const handleRemovePair = (index: number) => {
    const newPairs = pairs.filter((_, i) => i !== index);
    setPairs(newPairs);
    updateParent(newPairs);
  };

  const handleKeyChange = (index: number, newKey: string) => {
    const newPairs = [...pairs];
    newPairs[index].key = newKey;
    setPairs(newPairs);
    updateParent(newPairs);
  };

  const handleValueChange = (index: number, newValue: string) => {
    const newPairs = [...pairs];
    newPairs[index].value = newValue;
    setPairs(newPairs);
    updateParent(newPairs);
  };

  const updateParent = (newPairs: KeyValuePair[]) => {
    // Filter out empty pairs and convert to object
    const validPairs = newPairs.filter(p => p.key.trim() !== "");
    const obj = validPairs.reduce((acc, pair) => {
      acc[pair.key] = pair.value;
      return acc;
    }, {} as Record<string, string>);
    onChange(obj);
  };

  return (
    <div className="space-y-2">
      {pairs.map((pair, index) => (
        <div key={index} className="flex gap-2">
          <Input
            placeholder={placeholder?.key || "Key"}
            value={pair.key}
            onChange={(e) => handleKeyChange(index, e.target.value)}
            disabled={disabled}
            className="flex-1"
          />
          <Input
            placeholder={placeholder?.value || "Value"}
            value={pair.value}
            onChange={(e) => handleValueChange(index, e.target.value)}
            disabled={disabled}
            className="flex-1"
          />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => handleRemovePair(index)}
            disabled={disabled}
            className="h-10 w-10"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      ))}
      
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={handleAddPair}
        disabled={disabled}
        className="w-full"
      >
        <Plus className="mr-2 h-4 w-4" />
        Add {pairs.length === 0 ? "Key-Value Pair" : "Another"}
      </Button>
    </div>
  );
}
