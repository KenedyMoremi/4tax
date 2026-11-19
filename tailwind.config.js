module.exports = {
  content: ['./business_profiles/templates/**/*.html', './business_profiles/static/**/*.js', './templates/**/*.html', './whatsapp/templates/**/*.html', './bookkeeping/templates/**/*.html', './static/js/**/*.js', './bookkeeping/static/**/*.js'],
  safelist: ['badge-paid', 'badge-posted', 'badge-unpaid', 'badge-part', 'badge-overdue', 'badge-void'],
  theme: {extend: {colors: {brand: '#f65c00', ink: '#202320'}, fontFamily: {sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif']}}},
  plugins: [],
};
