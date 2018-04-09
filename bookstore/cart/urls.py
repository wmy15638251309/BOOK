from django.conf.urls import url
from cart import views
urlpatterns = [
	url(r'^add/$',views.cart_add,name='add'),#添加购物车数据
	url(r'^count/$',views.cart_count,name='count'),#获取用户购物车种商品的数量
	url(r'^$',views.cart_show,name='show'),#显示用户的购物页面
	url(r'^del/$',views.cart_del,name='delete'),#购物车商品记录删除
	url(r'^update/$',views.cart_uptate,name='update')
]