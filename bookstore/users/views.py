from django.http import JsonResponse
from django.shortcuts import render,redirect
import re
from users.models import *
from django.core.urlresolvers import reverse
from utils.decorators import *
# from django.views.decorators import csrf
# Create your views here.
def register(request):
	'''显示用户注册页面'''
	return render(request,'users/register.html')

def register_handle(request):
	# 进行用户注册处理
	#接收数据
	username = request.POST.get('user_name')
	password = request.POST.get('pwd')
	email = request.POST.get('email')

	#进行数据校验
	if not all([username,password,email]):
		#有数据为空
		return render(request,'users/register.html', {'errmsg':'参数不能为空!'})

	#判断邮箱是否合法
	if not re.match(r'^[a-z0-9][\w\.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$',email):
		return render(request,'users/register.html', {'errmsg':'邮箱不合法!'})

	#进行业务处理:注册,向账户系统添加账号
	# Passport.objects.create(username=username, password=password, email=email)
	passport = Passport.objects.add_one_passport(username=username,password=password,email=email)

	#注册完,还是返回注册页
	return redirect(reverse('books:index'))

def login(request):
	#显示登录页面
	username = ''
	checked = ''
	context = {
		'username':username,
		'checked':checked,
	}
	return render(request,'users/login.html',context)

def login_check(request):
	#进行用户登录校验
	username = request.POST.get('username')
	password = request.POST.get('password')
	remember = request.POST.get('remember')
	#数据校验
	if not all([username,password,remember]):
		#有数据为空
		return JsonResponse({'res':2})
	#进行处理:根据用户名和密码查找账户信息
	passport = Passport.objects.get_one_passport(username=username,password=password)
	if passport:
		#用户密码正确
		#获取session中的url_path
		# if request.session.has_key('url_path'):
		# 	next_url = request.session.get('url_path')
		# else:
		# 	next_url = reverse('books:index')
		next_url = request.session.get('url_path',reverse('books:index'))
		jres = JsonResponse({'res':1,'next_url':next_url})
		#判断是否需要记住用户名
		if remember == 'true':
			#记住用户名
			jres.set_cookie('username',username,max_age=7*24*3600)
		else:
			jres.delete_cookie('username')
		#记住用户的登录状态
		request.session['islogin'] = True
		request.session['username'] = username
		request.session['passport_id'] = passport.id
		return jres
	else:
		#用户名或密码错误
		return JsonResponse({'res':0})

def logout(request):
	#用户退出登录,清空用户的session的信息
	request.session.flush()
	return redirect(reverse('books:index'))


@login_required
# def user(request):
# 	# 用户中心＿信息页
# 	passport_id = request.session.get('passport_id')
# 	# 获取用户基本信息
# 	addr = Address.objects.get_default_address(passport_id=passport_id)
# 	books_li = []
# 	context = {
# 		'addr':addr,
# 		'page':'users',
# 		'books_li':books_li
# 	}
# 	return render(request,'users/user_center_info.html',context)
def user(request):
	'''用户中心-信息页'''
	passport_id = request.session.get('passport_id')
	# 获取用户的基本信息
	addr = Address.objects.get_default_address(passport_id=passport_id)

	books_li = []

	context = {
		'addr': addr,
		'page': 'user',
		'books_li': books_li
	}

	return render(request, 'users/user_center_info.html', context)



