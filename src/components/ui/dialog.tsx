"use client";

import * as React from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

export interface DialogProps {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  children?: React.ReactNode;
}

export interface DialogCloseEvent {
  source: "escape" | "backdrop" | "closeButton" | "select";
  data?: { label: string; value: string };
  scrollCancelled?: boolean;
}

export interface DialogDescriptionProps {
  children?: React.ReactNode;
  className?: string;
}

export function DialogDescription({ children, className }: DialogDescriptionProps) {
  return <p className={cn("text-sm text-zinc-600 dark:text-zinc-400", className)}>{children}</p>;
}

export interface DialogFooterProps {
  children?: React.ReactNode;
  className?: string;
}

export function DialogFooter({ children, className }: DialogFooterProps) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-end gap-2 pt-4 border-t border-zinc-100 dark:border-white/5",
        className
      )}
    >
      {children}
    </div>
  );
}

export interface DialogHeaderProps {
  children?: React.ReactNode;
  className?: string;
}

export function DialogHeader({ children, className }: DialogHeaderProps) {
  return (
    <div className={cn("flex flex-col space-y-1.5 p-5 pb-0", className)}>
      {children}
    </div>
  );
}

export interface DialogOverlayProps {
  className?: string;
  children?: React.ReactNode;
}

export function DialogOverlay({ className, children }: DialogOverlayProps) {
  return (
    <div
      className={cn(
        "fixed inset-0 z-50 bg-zinc-950/60 dark:bg-black/60 backdrop-blur-sm",
        className
      )}
    >
      {children}
    </div>
  );
}

export interface DialogPortalProps {
  children?: React.ReactNode;
}

export function DialogPortal({ children }: DialogPortalProps) {
  return <div className="fixed inset-0 z-50">{children}</div>;
}

export interface DialogProps {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  children?: React.ReactNode;
}

export function Dialog({ open = false, onOpenChange, children }: DialogProps) {
  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Escape") {
      e.preventDefault();
      onOpenChange?.(false);
    }
  };

  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) {
      onOpenChange?.(false);
    }
  };

  if (!open) return null;

  return (
    <DialogPortal>
      <DialogOverlay />
      <div
        role="dialog"
        aria-modal="true"
        onKeyDown={handleKeyDown}
        onClick={handleBackdropClick}
        className="fixed inset-0 z-50 flex items-center justify-center p-4"
      >
        {children}
      </div>
    </DialogPortal>
  );
}

export interface DialogTitleProps {
  children?: React.ReactNode;
  className?: string;
}

export function DialogTitle({ children, className }: DialogTitleProps) {
  return (
    <div
      className={cn(
        "flex items-center gap-2 text-base font-semibold text-zinc-900 dark:text-zinc-100",
        className
      )}
    >
      {children}
    </div>
  );
}

export interface DialogTriggerProps {
  children?: React.ReactNode;
  onClick?: () => void;
  className?: string;
}

export function DialogTrigger({ children, onClick, className }: DialogTriggerProps) {
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onClick?.();
      }}
      className={cn("inline-flex items-center justify-center", className)}
    >
      {children}
    </button>
  );
}

export interface DialogContentProps {
  children?: React.ReactNode;
  className?: string;
}

export function DialogContent({ children, className }: DialogContentProps) {
  return (
    <div
      className={cn(
        "relative z-50 max-w-lg w-full rounded-lg border border-zinc-200 dark:border-white/10 bg-white dark:bg-[#121214] shadow-lg",
        className
      )}
    >
      {children}
    </div>
  );
}

export interface DialogCloseProps {
  children?: React.ReactNode;
  onClick?: () => void;
  className?: string;
}

export function DialogClose({ children, onClick, className }: DialogCloseProps) {
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onClick?.();
      }}
      className={cn(
        "absolute top-4 right-4 rounded-md p-1 text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors",
        className
      )}
    >
      {children ?? <X className="h-4 w-4" />}
    </button>
  );
}

export interface DialogSelectProps {
  options: { label: string; value: string }[];
  onSelect: (option: { label: string; value: string }) => void;
  value?: string;
  className?: string;
  children?: React.ReactNode;
}

export function DialogSelect({
  options,
  onSelect,
  value,
  className,
  children,
}: DialogSelectProps) {
  const handleSelect = (option: { label: string; value: string }) => {
    onSelect(option);
  };

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      {children}
      <div className="flex flex-col gap-2 mt-2">
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => handleSelect(option)}
            className={cn(
              "flex items-center justify-between w-full px-4 py-3 rounded-md border text-sm transition-colors",
              option.value === value
                ? "bg-blue-50 dark:bg-blue-950/30 border-blue-500 dark:border-blue-500 text-blue-700 dark:text-blue-400"
                : "border-zinc-200 dark:border-white/10 text-zinc-700 dark:text-zinc-300 hover:border-zinc-300 dark:hover:border-white/20"
            )}
          >
            <span className="flex items-center gap-2">
              {option.value === value && (
                <span className="flex-shrink-0 w-5 h-5 rounded-full bg-blue-500 dark:bg-blue-500 flex items-center justify-center">
                  <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                </span>
              )}
              <span className="truncate">{option.label}</span>
            </span>
            {option.value === value && (
              <span className="text-xs font-mono text-zinc-500 dark:text-zinc-400">{option.value}</span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}

export interface DialogSelectGroupProps {
  children: React.ReactNode;
  className?: string;
}

export function DialogSelectGroup({ children, className }: DialogSelectGroupProps) {
  return <div className={cn("flex flex-col", className)}>{children}</div>;
}

export function useDialog(open: boolean, onOpenChange: (open: boolean) => void) {
  const handleClose = React.useCallback(
    (event: DialogCloseEvent) => {
      onOpenChange(false);
    },
    [onOpenChange]
  );

  return {
    isOpen: open,
    onClose: handleClose,
  };
}
