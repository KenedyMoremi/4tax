from django import forms


class RecommendationForm(forms.Form):
    consent = forms.BooleanField(
        label='Use my business summary to generate recommendations',
        help_text='Only sector, dates and aggregate figures are sent to Groq. Names, national IDs, contacts and individual transaction descriptions are excluded.',
    )
