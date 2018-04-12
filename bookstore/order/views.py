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
from alipay import AliPay

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
		'transit_price':transit_price,
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
	pay_method = request.POST.get('pay_method')
	books_ids = request.POST.get('books_ids')
	# 进行数据校验
	if not all([addr_id, pay_method, books_ids]):
		return JsonResponse({'res': 1, 'errmsg': '数据不完整'})
	try:
		addr = Address.objects.get(id=addr_id)
	except Exception as e:
		#地址信息出错
		return JsonResponse({'res':2,'errmsg':'地址信息错误'})
	if int(pay_method) not in OrderInfo.PAY_METHODS_ENUM.values():
		return JsonResponse({'res':3,'errmsg':'不支持的支付方式'})
	#订单创建　组织订单信息
	passport_id = request.session.get('passport_id')
	#订单ｉｄ:当前时间＋用户 id
	order_id = datetime.now().strftime('%Y%m%d%H%M%S') + str(passport_id)
	transit_price = 10
	total_count = 0
	total_price = 0
	#创建一个保存点
	sid = transaction.savepoint()
	try:
		#想订单信息表中添加一条记录
		order = OrderInfo.objects.create(order_id=order_id,
										 passport_id=passport_id,
										 addr_id=addr_id,
										 total_count=total_count,
										 total_price=total_price,
										 transit_price=transit_price,
										 pay_method=pay_method)
		#想订单商品表中添加订单商品的记录
		books_ids = books_ids.split(',')
		conn = get_redis_connection('default')
		cart_key = 'cart_%d' % passport_id
		#遍历获取用户购买的商品信息
		for id in books_ids:
			books = Books.objects.get_books_by_id(books_id=id)
			if books is None:
				transaction.savepoint_rollback(sid)
				return JsonResponse({'res':4,'errmsg':'商品信息错误'})
			#获取用户购买的商品数目
			count = conn.hget(cart_key,id)
			#判断商品库存
			if int(count) > books.stock:
				transaction.savepoint_rollback(sid)
				return JsonResponse({'res':5,'errmsg':'商品库存不足'})
			#创建一条订单商品记录
			OrderGoods.objects.create(order_id=order_id,
									  books_id=id,
									  count=count,
									  price=books.price)
			#增加商品销量　减少商品库存
			books.sales += int(count)
			books.stock -= int(count)
			books.save()
			#累计计算商品的总数目和总额
			total_count += int(count)
			total_price += int(count)*books.price
		#更新订单的商品总数目和总金额
		order.total_count = total_count
		order.total_price = total_price
		#保存在缓存中
		order.save()
	except Exception as e:
		#操作数据库出错 进行回滚操作
		transaction.savepoint_rollback(sid)
		return JsonResponse({'res':7,'errmsg':'服务器错误'})
	#清楚购物车对应记录
	conn.hdel(cart_key,*books_ids)
	transaction.savepoint_commit(sid) #事务提交
	return JsonResponse({'res':6}) #返回应答

def order_pay(request):
	'''订单支付'''
	if not request.session.has_key('islogin'):
		return JsonResponse({'res':0,'errmsg':'用户未登录'})
	#接受订单ｉｄ
	order_id = request.POST.get('order_id')
	#数据校验
	if not order_id:
		return JsonResponse({'res':1,'errmsg':'订单不存在'})
	try:
		order = OrderInfo.objects.get(order_id=order_id,
									  status=1,
									  pay_method=3)
	except OrderInfo.DoesNotExist:
		return JsonResponse({'res':2,'errmsg':'订单信息出错'})
	#和支付宝进行交互
	alipay = AliPay(
		appid = '2016090800464054',#应用ｉｄ
		app_notify_url = None,#默认回调
		app_private_key_path = os.path.join(settings.BASE_DIR,'order/app_private_key_path'),
		alipay_public_key_path = os.path.join(settings.BASE_DIR, 'order/alipay_public_key.pem'),  # 支付宝秘钥，
		sign_type = "RSA2",
		debug = True,
	)
	#网站支付跳转页面
	total_pay = order.total_price + order.transit_prize
	order_string = alipay.api_alipay_trade_page_pay(
		out_trade_no=order_id,
		total_amount=str(total_pay),
		subject='尚硅谷书城%s' % order_id,
		return_url=None,
		notify_url=None
	)
	pay_url = settings.ALLOWED_HOSTS + '?' + order_string
	return JsonResponse({'res':3,'pay_url':pay_url,'message':'OK'})

def check_pay(request):
	'''获取用户支付的结果'''
	if not request.session.has_key('islogin'):
		return JsonResponse({'res':0,'errmsg':'用户未登陆'})
	passport_id = request.session.get('passport_id')
	order_id = request.POST.get('order_id')
	#数据校验
	if not order_id:
		return JsonResponse({'res':1,'errmsg':'订单不存在'})
	try:
		order = OrderInfo.objects.get(order_id=order_id,
									  passport_id=passport_id,
									  pay_method=3)
	except OrderInfo.DoesNotExist:
		return JsonResponse({'res':2,'errmsg':'订单信息出错'})
	alipay = AliPay(
		appid = "2016090800464054",
		app_notify_url = None,
		app_private_key_path = os.path.join(settings.BASE_DIR, 'df_order/app_private_key.pem'),
		alipay_public_key_path = os.path.join(settings.BASE_DIR, 'df_order/alipay_public_key.pem'),
		# 支付宝的公钥验证支付宝回传消息使用 不是你的公钥,
		sign_type="RSA2",
		debug=True,
	)
	while True:
		#支付结果查询
		result = alipay.api_alipay_trade_query(order_id)
		code = result.get('code')
		if code == '10000' and result.get('trade_status') == 'TRADE_SUCCESS':
			#用户支付成功　　　改变订单支付状态
			order_status = 2 #待发货
			#填写支付宝交易号
			order.trade_id = result.get('trade_no')
			order.save()
			return JsonResponse({'res':3,'message':'支付成功'})
		elif code == '40004' or (code=='10000' and result.get('trade_status'=='WAIT_BUYER_PAY')):
			#订单未生成　用户还未支付　　都要继续查询
			time.sleep(5)
			continue
		else:
			return JsonResponse({'res':4,'errmsg':'支付出错'})


