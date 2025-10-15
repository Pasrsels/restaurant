from .models import Branch, User

def branches(request):
    return {'branches': Branch.objects.all()}

def cashiers(request):
    return {
        'cashiers':User.objects.filter(role='sales')
    }