import random
from django.http import Http404
from django.shortcuts import redirect, render, HttpResponse
from .models import urlModel
# Create your views here.
def home(request):
    return render(request, 'index.html')

def makeShortUrl(request):
    longurl = request.POST['longurl']
    s = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*"
    shorturl = ("".join(random.sample(s,6)))
    obj = urlModel.objects.create(longurl= longurl, shorturl=shorturl)
    print("object created")
    shorturl="http://127.0.0.1:8000/"+shorturl
    return HttpResponse("Your shorturl for {} is {} " .format(longurl,shorturl))

def redirecturl(request,shorturl):
	print(shorturl)
	try:
		obj = urlModel.objects.get(shorturl=shorturl)
	except urlModel.DoesNotExist:
		obj = None
	if obj:
		print("object found")
		print(obj.longurl)
		obj.count+=1
		obj.save()
		return redirect(obj.longurl)
	else:
		return Http404