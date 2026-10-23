import type React from 'react'
export function Chevron({ size = 8 }: { size?: number }) {
  return (
    <svg viewBox="0 0 8 12" width={size * 0.625} height={size} aria-hidden>
      <path d="M1.6 1.4 6.2 6l-4.6 4.6" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
/** ‹ pointing left (RTL "forward") */
export function ChevLeft({ size = 10 }: { size?: number }) {
  return (
    <svg viewBox="0 0 10 10" width={size} height={size} aria-hidden>
      <path d="M6.3 1.8 3.2 5l3.1 3.2" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
export function BackIcon() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden>
      <path d="M9 5l7 7-7 7" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
export function Plus({ size = 13 }: { size?: number }) {
  return (
    <svg viewBox="0 0 14 14" width={size} height={size} aria-hidden>
      <path d="M7 1.2v11.6M1.2 7h11.6" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
    </svg>
  )
}
export function Spark({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M12 2.5c.5 4.6 2.9 7 7.5 7.5-4.6.5-7 2.9-7.5 7.5-.5-4.6-2.9-7-7.5-7.5 4.6-.5 7-2.9 7.5-7.5Z" />
      <path d="M19 15c.2 1.8 1.2 2.8 3 3-1.8.2-2.8 1.2-3 3-.2-1.8-1.2-2.8-3-3 1.8-.2 2.8-1.2 3-3Z" opacity=".55" />
    </svg>
  )
}
export function Pin({ size = 15, color = '#e0565b' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" aria-hidden>
      <path d="M12 21s-7-6.1-7-11.5A7 7 0 0 1 19 9.5C19 14.9 12 21 12 21Z" />
      <circle cx="12" cy="9.5" r="2.4" fill={color} stroke="none" />
    </svg>
  )
}
export function Close() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden>
      <path d="M6 6l12 12M18 6 6 18" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  )
}
export function Heart({ on }: { on?: boolean }) {
  return (
    <svg viewBox="0 0 24 24" width="17" height="17" aria-hidden>
      <path d="M12 20.2s-7.6-4.6-7.6-10.1A4.3 4.3 0 0 1 12 7.6a4.3 4.3 0 0 1 7.6 2.5c0 5.5-7.6 10.1-7.6 10.1Z"
        fill={on ? '#e8506a' : 'none'} stroke="#e8506a" strokeWidth="1.9" strokeLinejoin="round" />
    </svg>
  )
}
export function Store() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
      <path d="M4 9.5V19a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1V9.5" /><path d="M3 9.5 4.6 4h14.8L21 9.5a3 3 0 0 1-6 0 3 3 0 0 1-6 0 3 3 0 0 1-6 0Z" /><path d="M9.5 20v-5h5v5" />
    </svg>
  )
}
export function Bookmark({ on }: { on?: boolean }) {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden>
      <path d="M6.5 4h11v16l-5.5-4-5.5 4Z" fill={on ? '#5b57d6' : 'none'} stroke={on ? '#5b57d6' : '#8a8a97'} strokeWidth="1.8" strokeLinejoin="round" />
    </svg>
  )
}
export function UserIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="#6b6c80" aria-hidden>
      <circle cx="12" cy="8.5" r="3.8" /><path d="M4.5 20c.6-4 3.7-6.2 7.5-6.2s6.9 2.2 7.5 6.2Z" />
    </svg>
  )
}
export function Send() {
  return (
    <svg viewBox="0 0 24 24" width="17" height="17" aria-hidden>
      <path d="M12 19V5M5.5 11.5 12 5l6.5 6.5" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

const S = (p: { size?: number; children: React.ReactNode; sw?: number }) => (
  <svg viewBox="0 0 24 24" width={p.size || 18} height={p.size || 18} fill="none" stroke="currentColor" strokeWidth={p.sw || 1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden>{p.children}</svg>
)
export const MapIcon = ({ size }: { size?: number }) => <S size={size}><path d="M9 4.5 3.5 6.5v13L9 17.5l6 2 5.5-2v-13L15 6.5l-6-2ZM9 4.5v13M15 6.5v13" /></S>
export const ShareIcon = ({ size }: { size?: number }) => <S size={size}><path d="M12 15V3.5M8 7.5l4-4 4 4M5.5 12v6.5a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2V12" /></S>
export const NavIcon = ({ size }: { size?: number }) => <S size={size}><path d="M20.5 3.5 3.5 10.6l7 2.9 2.9 7 7.1-17Z" /></S>
export const PhoneIcon = ({ size }: { size?: number }) => <S size={size}><path d="M8.2 3.5H5.6a1.6 1.6 0 0 0-1.6 1.8 16 16 0 0 0 14.7 14.7 1.6 1.6 0 0 0 1.8-1.6v-2.6l-3.6-1.5-1.8 1.8a11 11 0 0 1-5.2-5.2l1.8-1.8L8.2 3.5Z" /></S>
export const CopyIcon = ({ size }: { size?: number }) => <S size={size}><rect x="8.5" y="8.5" width="11" height="11" rx="2.4" /><path d="M15.5 8.5V6.4a2 2 0 0 0-2-2h-7a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h2" /></S>
export const CardIcon = ({ size }: { size?: number }) => <S size={size}><rect x="3.5" y="6" width="17" height="12.5" rx="2.4" /><path d="M3.5 10.5h17M7 15h3" /></S>
export const TruckIcon = ({ size }: { size?: number }) => <S size={size}><path d="M3.5 6.5h10v10h-10zM13.5 10h4l3 3.2v3.3h-7" /><circle cx="7" cy="17.5" r="1.7" /><circle cx="17" cy="17.5" r="1.7" /></S>
export const InstaIcon = ({ size }: { size?: number }) => <S size={size}><rect x="4" y="4" width="16" height="16" rx="4.6" /><circle cx="12" cy="12" r="3.6" /><circle cx="16.8" cy="7.3" r=".5" /></S>
export const GlobeIcon = ({ size }: { size?: number }) => <S size={size}><circle cx="12" cy="12" r="8.5" /><path d="M3.5 12h17M12 3.5c2.4 2.6 3.4 5.4 3.4 8.5s-1 5.9-3.4 8.5c-2.4-2.6-3.4-5.4-3.4-8.5s1-5.9 3.4-8.5Z" /></S>
export const PencilIcon = ({ size }: { size?: number }) => <S size={size}><path d="m5 19 1-4L15.5 5.5a2 2 0 0 1 3 3L9 18l-4 1Z" /></S>
export const SparkFill = ({ size = 14 }: { size?: number }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden><path d="M12 2.5c.6 4.6 3 7 7.6 7.6v.4c-4.6.6-7 3-7.6 7.6h-.4c-.6-4.6-3-7-7.6-7.6v-.4c4.6-.6 7-3 7.6-7.6h.4Z" fill="#8b84f0" /><path d="M19 15.5c.25 1.6 1 2.35 2.5 2.5v.2c-1.5.2-2.25.9-2.5 2.5h-.2c-.2-1.6-1-2.3-2.5-2.5V18c1.5-.15 2.3-.9 2.5-2.5h.2Z" fill="#b8b2ff" /></svg>
)
export const MetroIcon = ({ size = 14 }: { size?: number }) => <S size={size}><rect x="6" y="3.5" width="12" height="13" rx="3" /><path d="M6 11h12M9 20l1.5-3.5M15 20l-1.5-3.5" /><circle cx="9.3" cy="13.8" r=".6" /><circle cx="14.7" cy="13.8" r=".6" /></S>
export const CarIcon = ({ size = 14 }: { size?: number }) => <S size={size}><path d="M5 16.5v-4l1.8-4.2A2 2 0 0 1 8.6 7h6.8a2 2 0 0 1 1.8 1.3l1.8 4.2v4M4 12.5h16v4H4z" /><circle cx="7.5" cy="16.5" r="1.4" /><circle cx="16.5" cy="16.5" r="1.4" /></S>
export const WalkIcon = ({ size = 14 }: { size?: number }) => <S size={size}><circle cx="13" cy="4.8" r="1.6" /><path d="m10 20 2-5.5 2.5 2.5V20M8 12l2.5-4h3l2 3.5 2.5 1M12.5 14.5 11 8" /></S>
export const LocateIcon = ({ size = 15 }: { size?: number }) => <S size={size}><circle cx="12" cy="12" r="3.2" /><path d="M12 3.5v3M12 17.5v3M3.5 12h3M17.5 12h3" /></S>
