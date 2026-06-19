import { useState } from 'react';

// Attendant-facing kiosk reset. Lives at the right edge of the hero row on both
// kiosk screens. Always confirms before clearing, so a stray tap can't wipe a
// guest's screen before they've scanned their profile.
export default function ResetControl({ onConfirm }: { onConfirm: () => void }) {
  const [confirming, setConfirming] = useState(false);

  return (
    <>
      <button type="button" className="v4m-reset" onClick={() => setConfirming(true)}>
        New entry <span className="ico" aria-hidden="true">↻</span>
      </button>

      {confirming && (
        <div className="v4m-confirm-overlay" onClick={() => setConfirming(false)}>
          <div className="v4m-confirm-card" onClick={e => e.stopPropagation()}>
            <div className="v4m-confirm-title">Start a <span className="it">new entry?</span></div>
            <p className="v4m-confirm-sub">
              This clears the screen for the next player. Make sure they’ve scanned their profile first.
            </p>
            <div className="v4m-confirm-actions">
              <button type="button" className="v4m-confirm-cancel" onClick={() => setConfirming(false)}>
                Cancel
              </button>
              <button
                type="button"
                className="v4m-confirm-go"
                onClick={() => { setConfirming(false); onConfirm(); }}
              >
                New entry <span className="ico" aria-hidden="true">↻</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
