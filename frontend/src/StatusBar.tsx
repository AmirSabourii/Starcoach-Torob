export function StatusBar() {
  return (
    <div className="statusbar" dir="ltr" aria-hidden>
      <span className="sb-time">9:41</span>
      <span className="sb-icons">
        <svg className="sb-signal" viewBox="0 0 18 12" fill="#000">
          <rect x="0" y="7.6" width="3.2" height="4.4" rx="0.9" />
          <rect x="4.8" y="5.3" width="3.2" height="6.7" rx="0.9" />
          <rect x="9.6" y="2.8" width="3.2" height="9.2" rx="0.9" />
          <rect x="14.4" y="0" width="3.2" height="12" rx="0.9" />
        </svg>
        <svg className="sb-wifi" viewBox="0 0 16 12" fill="#000">
          <path d="M8 2.3c2.3 0 4.4.9 6 2.4.2.2.5.2.7 0l1.1-1.1c.2-.2.2-.5 0-.7A11.3 11.3 0 0 0 8 0C5 0 2.3 1.1.2 2.9c-.2.2-.2.5 0 .7l1.1 1.1c.2.2.5.2.7 0A8.6 8.6 0 0 1 8 2.3Z" />
          <path d="M8 6c1.3 0 2.4.5 3.3 1.3.2.2.5.2.7 0l1.1-1.1c.2-.2.2-.5 0-.7A7 7 0 0 0 8 3.6a7 7 0 0 0-5.1 1.9c-.2.2-.2.5 0 .7L4 7.3c.2.2.5.2.7 0C5.6 6.5 6.7 6 8 6Z" />
          <path d="M10.4 9.1c.2-.2.2-.5 0-.7A3.5 3.5 0 0 0 8 7.5c-.9 0-1.8.3-2.4.9-.2.2-.2.5 0 .7l2 2c.2.2.6.2.8 0l2-2Z" />
        </svg>
        <svg className="sb-battery" viewBox="0 0 27 13">
          <rect x="0.5" y="0.5" width="23" height="12" rx="3.6" fill="none" stroke="#000" strokeOpacity=".38" />
          <rect x="2" y="2" width="20" height="9" rx="2.3" fill="#000" />
          <path d="M25 4.4v4.2c.8-.3 1.4-1.1 1.4-2.1s-.6-1.8-1.4-2.1Z" fill="#000" fillOpacity=".42" />
        </svg>
      </span>
    </div>
  )
}
