from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import Ticket, UserProfile
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError


class TicketCreateForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ['ticket_type', 'purchaser_name', 'purchaser_email', 'purchaser_phone']
        widgets = {
            'ticket_type': forms.Select(attrs={'class': 'form-control'}),
            'purchaser_name': forms.TextInput(attrs={'placeholder': 'Full name'}),
            'purchaser_email': forms.EmailInput(attrs={'placeholder': 'Email (optional)'}),
            'purchaser_phone': forms.TextInput(attrs={'placeholder': 'Phone (optional)'}),
        }

    def clean_purchaser_phone(self):
        phone = (self.cleaned_data.get('purchaser_phone') or '').strip().replace(' ', '')
        if not phone:
            return phone
        if not phone.isdigit() or len(phone) != 10 or not phone.startswith('07'):
            raise forms.ValidationError('Enter a 10-digit number starting with 07.')
        return phone


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
    
class AdminPasswordChangeForm(forms.Form):
    """Lets an admin set a new password for any user without knowing the old one."""
    password1 = forms.CharField(
        label='New password',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'})
    )
    password2 = forms.CharField(
        label='Confirm new password',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'})
    )

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password1')
        p2 = cleaned.get('password2')

        if p1 and p2 and p1 != p2:
            self.add_error('password2', "The two passwords don't match.")

        if p1:
            try:
                validate_password(p1)
            except ValidationError as e:
                self.add_error('password1', e)

        return cleaned


