from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from permisions.permisions import admin_required
import csv
import pandas as pd
import matplotlib.pyplot as plt
from loguru import logger
from inventory.models import Production, ProductionItems

@admin_required
@login_required
def Dashboard(request):
    # logger.info('Starting')
    # p_plan = Production.objects.all()
    # p_plan_items_list = []

    # for id in p_plan:
    #     p_plan_items = ProductionItems.objects.filter(production__id = id.id)
    #     for items in p_plan_items:
    #         p_plan_items_list.append(
    #             [
    #                 id.date_created,
    #                 items.dish.name,
    #                 items.portions
    #             ]
    #         )
    # logger.info(p_plan_items_list)
    # p_plan_items_list.insert(0, ['Date', 'Dish', 'Portions'])
    # logger.info(p_plan_items_list)

    # with open('Production_Model.csv', 'w', newline='') as file:
    #     writer = csv.writer(file)
    #     writer.writerows(p_plan_items_list)

    # df = pd.read_csv('Production_Model.csv')
    # print(df.head())

    # X = df.iloc[1:,1].values
    # print(X[0:5])

    # y = df.iloc[1:,2].values
    # print(y[0:5])


    # plt.scatter(X,y)
    # plt.show()
    
    return render(request, 'dashboard.html')


