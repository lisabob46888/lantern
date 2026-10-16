import type { Config } from 'tailwindcss';

// Colours are CSS variables (src/index.css) so the dark and light themes share every class.
const v = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        page: v('page'),
        ink: v('ink'),
        muted: v('muted'),
        dim: v('dim'),
        faint: v('faint'),
        panel: v('panel'),
        bar: v('bar'),
        strip: v('strip'),
        line: v('line'),
        line2: v('line2'),
        edge: v('edge'),
        hover: v('hover'),
        chip: v('chip'),
        amber: 'var(--amber)',
        sky: 'var(--sky)',
      },
      fontFamily: {
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
        sans: ['"Helvetica Neue"', 'Helvetica', 'Arial', '"PingFang SC"', '"Noto Sans SC"', '"Microsoft YaHei"', 'sans-serif'],
      },
    },
  },
  plugins: [],
} satisfies Config;
