// Paletas ligadas as variaveis de index.css: o modo escuro troca as variaveis,
// nao as classes. So estas familias existem — uma cor fora delas (slate, red,
// blue...) nao muda no escuro, por isso o tema nao as oferece.
const shades = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950]
const palette = (name) => Object.fromEntries(
  shades.map((shade) => [shade, `rgb(var(--${name}-${shade}) / <alpha-value>)`])
)

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    colors: {
      transparent: 'transparent',
      current: 'currentColor',
      inherit: 'inherit',
      white: 'rgb(var(--white) / <alpha-value>)',
      black: '#000',
      zinc: palette('zinc'),
      emerald: palette('emerald'),
      rose: palette('rose'),
      amber: palette('amber'),
      sky: palette('sky'),
      brand: {
        DEFAULT: 'rgb(var(--brand) / <alpha-value>)',
        soft: 'rgb(var(--brand-soft) / <alpha-value>)',
        ink: 'rgb(var(--brand-ink) / <alpha-value>)',
      },
      // Texto sobre o verde vivo (emerald-500) — escuro nos dois temas.
      'on-accent': 'rgb(var(--on-accent) / <alpha-value>)',
    },
    extend: {
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', 'ui-sans-serif', 'system-ui', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'sans-serif'],
      },
      boxShadow: {
        card: '0 1px 2px rgba(24, 24, 27, 0.04), 0 1px 3px rgba(24, 24, 27, 0.06)',
        lift: '0 4px 12px -2px rgba(24, 24, 27, 0.08), 0 2px 4px -2px rgba(24, 24, 27, 0.05)',
        glow: '0 8px 24px -8px rgba(16, 185, 129, 0.45)',
      },
      keyframes: {
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'none' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'scale-in': {
          '0%': { opacity: '0', transform: 'scale(0.96)' },
          '100%': { opacity: '1', transform: 'none' },
        },
        'slide-down': {
          '0%': { opacity: '0', transform: 'translateY(-6px)' },
          '100%': { opacity: '1', transform: 'none' },
        },
        'grow-x': {
          '0%': { transform: 'scaleX(0)' },
          '100%': { transform: 'scaleX(1)' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-400px 0' },
          '100%': { backgroundPosition: '400px 0' },
        },
        // Saidas: espelho das entradas, mesma curva, ~60% da duracao.
        'fade-out': {
          '0%': { opacity: '1' },
          '100%': { opacity: '0' },
        },
        'scale-out': {
          '0%': { opacity: '1', transform: 'none' },
          '100%': { opacity: '0', transform: 'scale(0.96)' },
        },
        'slide-out-down': {
          '0%': { opacity: '1', transform: 'none' },
          '100%': { opacity: '0', transform: 'translateY(16px)' },
        },
        // Linha recem-criada: lavagem emerald-100 que some.
        'flash-emerald': {
          '0%': { backgroundColor: 'rgb(var(--emerald-100))' },
          '100%': { backgroundColor: 'transparent' },
        },
        // Traco do check; o path usa pathLength="1" e stroke-dasharray 1.
        'check-draw': {
          '0%': { strokeDashoffset: '1' },
          '100%': { strokeDashoffset: '0' },
        },
        // headShake do animate.css sem o rotateY (sem 3D): pedido recusado.
        nudge: {
          '0%, 100%': { transform: 'none' },
          '20%': { transform: 'translateX(-4px)' },
          '40%': { transform: 'translateX(3px)' },
          '60%': { transform: 'translateX(-2px)' },
          '80%': { transform: 'translateX(1px)' },
        },
      },
      animation: {
        'fade-up': 'fade-up 0.45s cubic-bezier(0.22, 1, 0.36, 1) both',
        'fade-in': 'fade-in 0.3s ease-out both',
        'scale-in': 'scale-in 0.25s cubic-bezier(0.22, 1, 0.36, 1) both',
        'slide-down': 'slide-down 0.2s ease-out both',
        'grow-x': 'grow-x 0.7s cubic-bezier(0.22, 1, 0.36, 1) both',
        shimmer: 'shimmer 1.4s linear infinite',
        'fade-out': 'fade-out 0.16s cubic-bezier(0.22, 1, 0.36, 1) both',
        'scale-out': 'scale-out 0.16s cubic-bezier(0.22, 1, 0.36, 1) both',
        'slide-out-down': 'slide-out-down 0.2s cubic-bezier(0.22, 1, 0.36, 1) both',
        // Esqueleto so aparece se a carga passar de 150ms: SQLite local
        // costuma responder antes, e ai nada pisca.
        skeleton: 'fade-in 0.2s cubic-bezier(0.22, 1, 0.36, 1) 150ms both, shimmer 1.4s linear 150ms infinite',
        // Sem fill: depois do flash a linha volta ao proprio fundo.
        'flash-emerald': 'flash-emerald 1.6s cubic-bezier(0.22, 1, 0.36, 1)',
        'check-draw': 'check-draw 0.35s cubic-bezier(0.22, 1, 0.36, 1) 80ms both',
        nudge: 'nudge 0.36s cubic-bezier(0.22, 1, 0.36, 1)',
      },
      transitionTimingFunction: {
        'out-quint': 'cubic-bezier(0.22, 1, 0.36, 1)',
      },
    },
  },
  plugins: [],
}
