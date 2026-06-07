from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import Ticket, UserProfile


class TicketCreateForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ['purchaser_name', 'purchaser_email', 'purchaser_phone']
        widgets = {
            'purchaser_name': forms.TextInput(attrs={'placeholder': 'Full name'}),
            'purchaser_email': forms.EmailInput(attrs={'placeholder': 'Email (optional)'}),
            'purchaser_phone': forms.TextInput(attrs={'placeholder': 'Phone (optional)'}),
        }


class UserCreateForm(UserCreationForm):
    role = forms.ChoiceField(choices=UserProfile.ROLES)
    email = forms.EmailField(required=False)

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2', 'role']


class UserEditForm(forms.ModelForm):
    role = forms.ChoiceField(choices=UserProfile.ROLES)

    class Meta:
        model = User
        fields = ['username', 'email', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and hasattr(self.instance, 'profile'):
            self.fields['role'].initial = self.instance.profile.role


class ScanForm(forms.Form):
    ticket_token = forms.CharField(
        widget=forms.HiddenInput(),
        required=False
    )
