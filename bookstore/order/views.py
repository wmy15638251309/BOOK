from django.shortcuts import render,redirect
from django.core.urlresolvers import reverse
from utils.decorators import login_required
from django.http import HttpResponse,JsonResponse
from users.models import Address
from books.models import Books
from order.models import OrderInfo, OrderGoods
from django_redis import get_redis_connection
from datetime import datetime
from django.conf import settings
import os
import time
from django.db import transaction

# Create your views here.

@login_required
def order_place(request):
	'''显示提交订单页面'''
	#接收数据
	books_ids = request.POST.getlist('books_ids')
	#校验数据　
	if not all(books_ids):
		#跳转　购物车页面
		return redirect(reverse('cart:show'))
	#用户收货地址
	passport_id = request.session.get('passport_id')
	addr = Address.objects.get_default_address(passport_id=passport_id)

	#用户要购买的商品信息
	books_li = []
	#商品的总数目和总金额
	total_count = 0
	total_price = 0
	conn = get_redis_connection('default')
	cart_key = 'cart_%d' % passport_id
	for id in books_ids:
		#根据ｉｄ获取商品的信息
		books = Books.objects.get_books_by_id(books_id=id)
		#从redis中获取用户要购买的商品的数目
		count = conn.hget(cart_key,id)
		books.count = count
		#计算商品的小计
		amount = int(count)*books.price
		books.amount = amount
		books_li.append(books)
		#累计计算商品总数目总金额
		total_count += int(count)
		total_price += books.amount
	#商品运费和实付款
	transit_price = 10
	total_pay = total_price + transit_price
	books_ids = ','.join(books_ids)
	context = {
		'addr':addr,
		'books_li':books_li,
		'total_count':total_count,
		'total_price':total_price,
		'total_pay':total_pay,
		'books_ids':books_ids,
	}
	return render(request,'order/place_order.html',context)

@transaction.atomic
def order_commit(request):
	'''生成订单'''
	#验证用户是否登录
	if not request.session.has_key('islogin'):
		return JsonResponse({'res':0,'errmsg':'用户未登录'})
	#接收数据
	addr_id = request.POST.get('addr_id')
