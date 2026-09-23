"use client";

import * as React from "react";
import * as ScrollAreaPrimitive from "@radix-ui/react-scroll-area";

import { cn } from "./utils";

// Enhanced types for better type safety
interface ScrollAreaProps extends React.ComponentProps<typeof ScrollAreaPrimitive.Root> {
  className?: string;
  children: React.ReactNode;
}

interface ScrollBarProps extends React.ComponentProps<typeof ScrollAreaPrimitive.ScrollAreaScrollbar> {
  className?: string;
  orientation?: "vertical" | "horizontal";
}

interface KeyboardScrollAreaProps {
  children: React.ReactNode;
  className?: string;
  maxHeight?: string;
  scrollAmount?: number;
  smoothScroll?: boolean;
  enableKeyboardNav?: boolean;
  ariaLabel?: string;
}

const ScrollArea = React.forwardRef<
  React.ElementRef<typeof ScrollAreaPrimitive.Root>,
  ScrollAreaProps
>(({ className, children, ...props }, ref) => (
  <ScrollAreaPrimitive.Root
    ref={ref}
    data-slot="scroll-area"
    className={cn("relative", className)}
    {...props}
  >
    <ScrollAreaPrimitive.Viewport
      data-slot="scroll-area-viewport"
      className="focus-visible:ring-ring/50 size-full rounded-[inherit] transition-[color,box-shadow] outline-none focus-visible:ring-[3px] focus-visible:outline-1"
    >
      {children}
    </ScrollAreaPrimitive.Viewport>
    <ScrollBar />
    <ScrollAreaPrimitive.Corner />
  </ScrollAreaPrimitive.Root>
));

ScrollArea.displayName = ScrollAreaPrimitive.Root.displayName;

const ScrollBar = React.forwardRef<
  React.ElementRef<typeof ScrollAreaPrimitive.ScrollAreaScrollbar>,
  ScrollBarProps
>(({ className, orientation = "vertical", ...props }, ref) => (
  <ScrollAreaPrimitive.ScrollAreaScrollbar
    ref={ref}
    data-slot="scroll-area-scrollbar"
    orientation={orientation}
    className={cn(
      "flex touch-none p-px transition-colors select-none",
      orientation === "vertical" &&
        "h-full w-2.5 border-l border-l-transparent",
      orientation === "horizontal" &&
        "h-2.5 flex-col border-t border-t-transparent",
      className,
    )}
    {...props}
  >
    <ScrollAreaPrimitive.ScrollAreaThumb
      data-slot="scroll-area-thumb"
      className="bg-border relative flex-1 rounded-full"
    />
  </ScrollAreaPrimitive.ScrollAreaScrollbar>
));

ScrollBar.displayName = ScrollAreaPrimitive.ScrollAreaScrollbar.displayName;

const KeyboardScrollArea = React.forwardRef<HTMLDivElement, KeyboardScrollAreaProps>(
  ({ 
    children, 
    className = "", 
    maxHeight = "70vh",
    scrollAmount = 50,
    smoothScroll = true,
    enableKeyboardNav = true,
    ariaLabel = "Scrollable content area"
  }, ref) => {
    const internalRef = React.useRef<HTMLDivElement>(null);
    const scrollRef = ref || internalRef;

    const scrollTo = React.useCallback((newScrollTop: number) => {
      const element = (scrollRef as React.RefObject<HTMLDivElement>).current;
      if (!element) return;

      if (smoothScroll) {
        element.scrollTo({
          top: newScrollTop,
          behavior: 'smooth'
        });
      } else {
        element.scrollTop = newScrollTop;
      }
    }, [smoothScroll, scrollRef]);

    React.useEffect(() => {
      if (!enableKeyboardNav) return;

      const handleKeyDown = (e: KeyboardEvent) => {
        const element = (scrollRef as React.RefObject<HTMLDivElement>).current;
        if (!element) return;
        
        const activeElement = document.activeElement;
        const isWithinScrollArea = element.contains(activeElement) || element === activeElement;
        
        if (!isWithinScrollArea) return;

        const currentScrollTop = element.scrollTop;
        const clientHeight = element.clientHeight;
        const scrollHeight = element.scrollHeight;

        switch (e.key) {
          case 'ArrowDown':
            e.preventDefault();
            scrollTo(Math.min(currentScrollTop + scrollAmount, scrollHeight - clientHeight));
            break;
          case 'ArrowUp':
            e.preventDefault();
            scrollTo(Math.max(currentScrollTop - scrollAmount, 0));
            break;
          case 'PageDown':
            e.preventDefault();
            scrollTo(Math.min(currentScrollTop + clientHeight * 0.8, scrollHeight - clientHeight));
            break;
          case 'PageUp':
            e.preventDefault();
            scrollTo(Math.max(currentScrollTop - clientHeight * 0.8, 0));
            break;
          case 'Home':
            if (e.ctrlKey) {
              e.preventDefault();
              scrollTo(0);
            }
            break;
          case 'End':
            if (e.ctrlKey) {
              e.preventDefault();
              scrollTo(scrollHeight - clientHeight);
            }
            break;
        }
      };

      document.addEventListener('keydown', handleKeyDown);
      
      return () => {
        document.removeEventListener('keydown', handleKeyDown);
      };
    }, [enableKeyboardNav, scrollAmount, scrollTo]);

    // Focus management for better accessibility
    const handleFocus = () => {
      const element = (scrollRef as React.RefObject<HTMLDivElement>).current;
      if (element && enableKeyboardNav) {
        element.setAttribute('data-keyboard-focused', 'true');
      }
    };

    const handleBlur = () => {
      const element = (scrollRef as React.RefObject<HTMLDivElement>).current;
      if (element) {
        element.removeAttribute('data-keyboard-focused');
      }
    };

    return (
      <div
        ref={scrollRef}
        className={cn(
          "overflow-y-auto pr-4 focus:outline-none rounded-sm",
          className
        )}
        style={{ maxHeight,outlineColor:"transparent" }}
        tabIndex={enableKeyboardNav ? 0 : -1}
        role="region"
        aria-label={ariaLabel}
        onFocus={handleFocus}
        onBlur={handleBlur}
        data-keyboard-nav={enableKeyboardNav}
      >
        {children}
      </div>
    );
  }
);

KeyboardScrollArea.displayName = "KeyboardScrollArea";

// Enhanced ScrollArea with keyboard navigation built-in
const ScrollAreaWithKeyboard = React.forwardRef<
  HTMLDivElement,
  ScrollAreaProps & KeyboardScrollAreaProps
>(({ children, className, maxHeight, scrollAmount, smoothScroll, enableKeyboardNav, ariaLabel, ...props }, ref) => (
  <ScrollArea className={className} {...props}>
    <KeyboardScrollArea
      ref={ref}
      maxHeight={maxHeight}
      scrollAmount={scrollAmount}
      smoothScroll={smoothScroll}
      enableKeyboardNav={enableKeyboardNav}
      ariaLabel={ariaLabel}
    >
      {children}
    </KeyboardScrollArea>
  </ScrollArea>
));

ScrollAreaWithKeyboard.displayName = "ScrollAreaWithKeyboard";

export { 
  ScrollArea, 
  ScrollBar, 
  KeyboardScrollArea, 
  ScrollAreaWithKeyboard 
};