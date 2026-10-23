import type React from 'react'
const S = ({ size = 18, children, sw = 1.8 }: { size?: number; children: React.ReactNode; sw?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round" aria-hidden>{children}</svg>
)
export const CameraIcon = ({ size }: { size?: number }) => <S size={size}><path d="M4 8.5A2 2 0 0 1 6 6.5h1.6l1.2-2h6.4l1.2 2H18a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8.5Z" /><circle cx="12" cy="12.5" r="3.4" /></S>
export const GalleryIcon = ({ size }: { size?: number }) => <S size={size}><rect x="3.8" y="4.8" width="16.4" height="14.4" rx="2.6" /><circle cx="9" cy="10" r="1.6" /><path d="m4.5 17.5 4.6-4.4 3.3 3 2.6-2.4 4.6 4.1" /></S>
export const RetryIcon = ({ size }: { size?: number }) => <S size={size}><path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3" /><path d="M19.6 4.5v3.6H16" /></S>
export const ShareIcon = ({ size }: { size?: number }) => <S size={size}><path d="M12 15V3.8M8 7.6l4-3.8 4 3.8M5.5 12v6.4a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2V12" /></S>
export const CloseIcon = ({ size = 16 }: { size?: number }) => <S size={size} sw={2.2}><path d="M6.5 6.5l11 11M17.5 6.5l-11 11" /></S>
export const BackIcon = ({ size = 20 }: { size?: number }) => <S size={size} sw={2.1}><path d="M9.5 5.5 16 12l-6.5 6.5" /></S>
export const ChevLeft = ({ size = 10 }: { size?: number }) => (
  <svg viewBox="0 0 10 10" width={size} height={size} aria-hidden><path d="M6.3 1.8 3.2 5l3.1 3.2" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" /></svg>
)
export const SparkIcon = ({ size = 18 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden>
    <path d="M11 3c.6 4.4 2.6 6.4 7 7-4.4.6-6.4 2.6-7 7-.6-4.4-2.6-6.4-7-7 4.4-.6 6.4-2.6 7-7Z" />
    <path d="M18.5 14.5c.25 1.7 1.05 2.5 2.75 2.75-1.7.25-2.5 1.05-2.75 2.75-.25-1.7-1.05-2.5-2.75-2.75 1.7-.25 2.5-1.05 2.75-2.75Z" opacity=".7" />
  </svg>
)
