module.exports = {
  content: ['./templates/**/*.html', './static/js/**/*.js'],
  safelist: ['badge-paid', 'badge-posted', 'badge-unpaid', 'badge-part', 'badge-overdue', 'badge-void'],
  theme: {extend: {colors: {brand: '#f65c00', ink: '#202320'}, fontFamily: {sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif']}}},
  plugins: [],
};
