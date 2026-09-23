import { Moon, Sun } from "lucide-react";
import { useTheme } from "../providers/ThemeProvider";
import { Button } from "./ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./ui/tooltip";

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            onClick={toggleTheme}
            className="h-9 w-9 p-0"
            aria-label="Toggle theme"
          >
            {theme === "light" ? (
              <Moon className="h-4 w-4 transition-transform duration-300" />
            ) : (
              <Sun className="h-4 w-4 transition-transform duration-300" />
            )}
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          <p>{theme === "light" ? "Switch to dark mode" : "Switch to light mode"}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
