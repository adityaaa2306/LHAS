import React from 'react';
import { ChevronDown } from 'lucide-react';

interface ScrollFadePanelProps {
  children: React.ReactNode;
  heightClassName?: string;
  className?: string;
  contentClassName?: string;
}

export const ScrollFadePanel: React.FC<ScrollFadePanelProps> = ({
  children,
  heightClassName = 'h-[34rem]',
  className = '',
  contentClassName = '',
}) => {
  const scrollRef = React.useRef<HTMLDivElement | null>(null);
  const [canScrollDown, setCanScrollDown] = React.useState(false);

  const updateScrollState = React.useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const remaining = el.scrollHeight - el.scrollTop - el.clientHeight;
    setCanScrollDown(remaining > 12);
  }, []);

  React.useEffect(() => {
    updateScrollState();
    const el = scrollRef.current;
    if (!el) return;

    const raf = requestAnimationFrame(updateScrollState);

    const resizeObserver = new ResizeObserver(() => updateScrollState());
    resizeObserver.observe(el);
    Array.from(el.children).forEach((child) => resizeObserver.observe(child));

    const mutationObserver = new MutationObserver(() => updateScrollState());
    mutationObserver.observe(el, { childList: true, subtree: true });

    return () => {
      cancelAnimationFrame(raf);
      resizeObserver.disconnect();
      mutationObserver.disconnect();
    };
  }, [children, updateScrollState]);

  const handleWheel = (event: React.WheelEvent<HTMLDivElement>) => {
    const el = scrollRef.current;
    if (!el) return;
    const hasOverflow = el.scrollHeight > el.clientHeight;
    if (!hasOverflow) return;

    const movingDown = event.deltaY > 0;
    const movingUp = event.deltaY < 0;
    const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 1;
    const atTop = el.scrollTop <= 0;

    if ((movingDown && !atBottom) || (movingUp && !atTop)) {
      event.stopPropagation();
    }
  };

  const scrollDown = () => {
    scrollRef.current?.scrollBy({
      top: Math.max((scrollRef.current?.clientHeight || 240) * 0.8, 180),
      behavior: 'smooth',
    });
  };

  return (
    <div className={`relative min-h-0 overflow-hidden rounded-2xl ${heightClassName} ${className}`}>
      <div
        ref={scrollRef}
        onWheel={handleWheel}
        onScroll={updateScrollState}
        style={{ WebkitOverflowScrolling: 'touch', touchAction: 'pan-y' }}
        className={`h-full min-h-0 overflow-y-auto overscroll-contain scroll-smooth pr-2 [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden ${contentClassName}`}
      >
        {children}
      </div>

      {canScrollDown && (
        <>
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-24 rounded-b-2xl bg-gradient-to-b from-transparent via-neutral-950/6 to-neutral-950/28" />
          <div className="pointer-events-none absolute inset-x-0 bottom-4 flex justify-center">
            <button
              type="button"
              onClick={scrollDown}
              className="pointer-events-auto inline-flex h-10 w-10 items-center justify-center rounded-full border border-white/70 bg-white/90 text-neutral-700 shadow-[0_10px_30px_rgba(15,23,42,0.16)] backdrop-blur-md transition hover:-translate-y-0.5 hover:bg-white hover:text-neutral-900 motion-safe:animate-[scrollCue_1.8s_ease-in-out_infinite]"
              aria-label="Scroll down"
            >
              <ChevronDown size={16} className="drop-shadow-sm" />
            </button>
          </div>
          <div className="pointer-events-none absolute inset-x-8 bottom-0 h-px bg-gradient-to-r from-transparent via-neutral-300/80 to-transparent" />
        </>
      )}

      <style>{`
        @keyframes scrollCue {
          0%, 100% { transform: translateY(0); opacity: 0.88; }
          50% { transform: translateY(4px); opacity: 1; }
        }
      `}</style>
    </div>
  );
};
