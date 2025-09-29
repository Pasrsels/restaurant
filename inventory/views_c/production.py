from inventory.helpers.imports import *

@login_required   
def production_plans(request):
    """
        production plan list view
    """
    plans = Production.objects.filter(branch=request.user.branch).select_related('branch')
    transfer_count = Transfer.objects.filter(status=False, branch=request.user.branch).count()

    plans = plans.annotate(
        total_actual=Sum(F('productionitems__declared_quantity') * F('productionitems__dish__cost'),
                         output_field=DecimalField(max_digits=12, decimal_places=2)),
        total_planned=Sum(F('productionitems__portions') * F('productionitems__dish__cost'),
                          output_field=DecimalField(max_digits=12, decimal_places=2)),
    ).annotate(
        total_variance=F('total_planned') - F('total_actual'),
    ).annotate(
        revenue=Sum(F('productionitems__portions_sold') * F('productionitems__dish__price'),
                    output_field=DecimalField(max_digits=12, decimal_places=2)),      
    ).order_by('-id')

    if request.user.role in ['chef', 'stores_person']:
        if request.user.role == 'stores_person':
            declaration_plans = Production.objects.filter(
                branch=request.user.branch,
                status=True, 
                declared=False  
            ).order_by('date_created')
        else:
            declaration_plans = plans
            
        context = {
            'plans': plans, 
            'declaration_plans': declaration_plans,
            'transfer_count': transfer_count,
            'selected_date': None,
            'today': datetime.now().date(),
            'yesterday': datetime.now().date() - timedelta(days=1),
        }
        
        return render(request, 'inventory/production_plans_chef.html', context)

    return render(request, 'inventory/production_plans.html', {
        'plans': plans, 
        'transfer_count': transfer_count
    })
    
def production_detail(request, pp_id):
    if request.method == 'GET':
        try:
            production_plan = Production.objects.select_related().get(id=pp_id, branch=request.user.branch)
            form = ProductionPlanInlineForm()
            production_plan_items = ProductionItems.objects.filter(production=production_plan)
            allocated_raw_materials = AllocatedRawMaterials.objects.filter(production=production_plan)
            print(allocated_raw_materials)
            
            raw_materials = []
            dish_details = []
            allocated_raw_materials = []
            total_cost = 0
            total_price = 0
            total_portions = 0

            for item in production_plan_items:
                    total_portions += item.portions
                    dish_details.append(
                        {
                            'name': item.dish.name,
                            'cost': item.dish.cost,
                            'total_price': round(item.dish.price * Decimal(item.portions), 2)
                        }
                    )
                    total_price += round(item.dish.price * Decimal(item.portions), 2)
                    for ing in Ingredient.objects.filter(dish=item.dish, minor_raw_material__branch=request.user.branch):
                        
                        p_r_m_bf, created = ProductionRawMaterials.objects.get_or_create(
                            product=ing.minor_raw_material,
                            defaults={
                                'quantity': 0
                            } 
                        )
                        
                        quantity = round(ing.quantity * (item.portions / item.dish.portion_multiplier), 3)
                    
                        raw_material_found = next((rm for rm in raw_materials if rm['id'] == ing.minor_raw_material.id), None)
                        
                        if raw_material_found:
                            
                            raw_material_found['quantity'] += round(float(quantity), 3)
                            raw_material_found['cost'] = round(Decimal(raw_material_found['quantity']) * ing.minor_raw_material.cost, 2)
                        else:
                            
                            raw_materials.append(
                                {
                                    'id': ing.minor_raw_material.id,
                                    'name': ing.minor_raw_material.name,
                                    'quantity': round(float(quantity), 3),
                                    'unit': ing.minor_raw_material.unit.unit_name,
                                    'cost': round(Decimal(ing.minor_raw_material.cost) * Decimal(quantity), 2),
                                }
                            )
                        
                        raw_material_prod = Product.objects.get(id = ing.minor_raw_material.id)


                        raw_material_prod_found = next((rm for rm in allocated_raw_materials if rm['id'] == raw_material_prod.id), None)

                        if raw_material_prod_found:
                            pass
                        else:
                            allocated_raw_materials.append(
                                {
                                    'id': raw_material_prod.id,
                                    'name': raw_material_prod.name,
                                    'quantity': round(float(raw_material_prod.quantity), 3),
                                    'unit': raw_material_prod.unit.unit_name,
                                    'cost': round(Decimal(raw_material_prod.cost) * Decimal(raw_material_prod.quantity), 2),
                                }
                            )
    
            allocated_raw_material_total_cost = 0
            allocated_raw_material_total_qnty = 0
            
            for items in allocated_raw_materials:
                allocated_raw_material_total_cost += items['cost']
                allocated_raw_material_total_qnty += items['quantity']

            for cost in raw_materials:
                total_cost += cost['cost']
                
            context =  {
                'p_plan': production_plan,
                'production_plan': production_plan_items,
                'ingridients':raw_materials,
                'allocated': allocated_raw_materials,
                'production_plan_id': pp_id,
                'total_price': dish_details,
                'total': total_cost,
                'total_portions': total_portions,
                'price': total_price,
                'form': form,
                'all_r_m_cost':allocated_raw_material_total_cost,
                'all_r_m_qnty':allocated_raw_material_total_qnty,
            }
        
            html = render(request, "production/partials/production_detail.html", context).content.decode("utf-8")
            return JsonResponse({"html": html})

        except Production.DoesNotExist:
            messages.warning(request, f'Production Plan With ID: {pp_id} doesn\'t exist.')
            return redirect('inventory:production_plan_detail', pp_id)
    
        
    if request.method == 'POST':
        data = json.loads(request.body)

        dish_name = data.get('dish_name').split('@')[0].strip()
        portions = data.get('portions')

        try:
            dish_ing = Ingredient.objects.filter(dish__name = dish_name, minor_raw_material__branch=request.user.branch)
            ingridient_list = []

            for ingridient in dish_ing:
                portion_m = ingridient.dish.portion_multiplier
                qnty = ingridient.quantity

                prop = qnty/portion_m
                declared_total_qnty = prop * int(portions)
                ingridient_list.append({
                    'ingridient_name': ingridient.minor_raw_material.name,
                    'ingridient_qnty': round(declared_total_qnty, 3)
                })
                
            with transaction.atomic():
                production = Production.objects.get(id=pp_id, branch=request.user.branch)
                production_item = ProductionItems.objects.get(production=production, dish__name=dish_name)
                production_item.declared_quantity = float(portions)
                production_item.save()
                
                eod, created = EndOfDay.objects.get_or_create(date=datetime.datetime.now(), branch=request.user.branch, done=False)
                eod_item = EndOfDayItems.objects.filter(end_of_day=eod, dish_name=dish_name).first()
                eod_item.declared = float(portions)
                eod_item.expected = production_item.portions
                eod_item.save()
                
                logger.success(f'Successfully updated EOD item for dish: {dish_name} with declared portions: {portions}')
                return JsonResponse({'success':True, 'ingridient': ingridient_list}, status = 200)
        except Exception as e:
            logger.error(f'Error: {e}')
            return JsonResponse({'success': False}, status= 400)
        
    elif request.method == 'PUT':
        try:
            data = json.loads(request.body)
            ing_data = data.get('data', '')
            dish_data = data.get('data_dish', '')
            
            logger.info({
                'ING': ing_data,
                'DISH': dish_data
            })

            try:
                production= Production.objects.get(id=pp_id, branch=request.user.branch)
            except ProductionItems.DoesNotExist:
                return JsonResponse({'success': False, 'message': f'Production Plan with ID: {pp_id} doesn\'t exist'}, status=404)

            edit_pplan_portions = []

            for ing in ing_data:
                logger.info({
                    'name': ing.get('ingridient_name'),
                    'used_qnty': ing.get('system'),
                    'variance': ing.get('variance')
                })
            
                # try:
                #     allocated = AllocatedRawMaterials.objects.get(raw_material__name=ing.get('ingridient_name'), production=production)
                # except ProductionItems.DoesNotExist:
                #     return JsonResponse({'success': False, 'message': f'Raw Material with ID: {ing.get('ingridient_name')} doesn\'t exist'}, status=404)

                try:
                    product = Product.objects.get(name=ing.get('ingridient_name'), branch=request.user.branch)
                    p_rm_variance = ProductionVariance.objects.create(
                        production=production,
                        ingredient=product,
                        quantity=float(ing.get('variance'))
                    )
                    logger.info(p_rm_variance)
                except ProductionVariance.DoesNotExist:
                    return JsonResponse({'success': False, 'message': f'Variance for Raw Material with ID: {ing.get('ingridient_name')} doesn\'t exist'}, status=404)
                
                with transaction.atomic():
                    p_rm = ProductionRawMaterials.objects.get(product__name=ing.get('ingridient_name'))
                    p_rm.quantity -= float(ing.get('system'))
                    
                    
                    # allocated.remaining_quantity = allocated.quantity - float(ing.get('system'))
                    # allocated.save()
                    
                    ProductionLogs.objects.create(
                        user=request.user, 
                        action= 'declared',
                        description='from warehouse',
                        product=p_rm,
                        quantity=p_rm.quantity,
                        total_quantity=p_rm.quantity,
                    )
                    p_rm.save()
    
            try:
                production = Production.objects.get(id=pp_id, branch=request.user.branch)  
                production_plan_items = ProductionItems.objects.filter(production=production)
                total_cost = production_plan_items.aggregate(total_cost=Sum('total_cost'))['total_cost'] or 0
            except Production.DoesNotExist:
                return JsonResponse({'success':False, 'message':f'Production with ID: {pp_id}, doesn\'t exists'})
    
            declaration_flag = True
            with transaction.atomic():
                COGS.objects.create(
                    production=production,
                    amount=total_cost,
                    # branch=request.user.branch
                )
                
                if declaration_flag:
                    
                    production.declared = True
                    production.save()
            
            for dish in dish_data:
                logger.info({
                    'name': dish.get('dish_name'),
                    'p_portions': dish.get('planned_portions'),
                    'declared': dish.get('declared'),
                    'note': dish.get('note', '')
                })
                if dish.get('note'):
                    note = dish.get('note', '')
                    extra_portions = Decimal(note.split(':')[1].strip())
                    edit_pplan_portions.append(
                        {
                            'name': dish.get('dish_name'),
                            'portions': dish.get('declared'),
                            'planned_portions': dish.get('planned_portions'),
                            'add_portions': extra_portions
                        }
                    )

            logger.info(edit_pplan_portions)
            if edit_pplan_portions:
                editProdPlan(prod_id=pp_id, data=edit_pplan_portions)

            return JsonResponse({'success': True})
        except Exception as e:
            logger.error(f'Error: {e}')
            return JsonResponse({'success':False})


@login_required
@transaction.atomic
def create_production_plan(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            items = data.get('cart', [])
            production_plan = None
            auto_confirm = data.get('auto', '')

            if not items:
                return JsonResponse({'success': False, 'message': 'Invalid data: items should be a list'}, status=400)

            if auto_confirm:
                if data.get('id'):
                    production_plan = Production.objects.get(id = data.get('id'), branch=request.user.branch)
                else:
                    production_latest = Production.objects.filter(date_created = datetime.date.today(), branch=request.user.branch).order_by('-time_created').first()
                    if production_latest:
                        production_plan = production_latest
                    else:
                        return JsonResponse({'success': False, 'message': 'No production Plan for Today.'}, status=400)
            else:
                # Create a new production plan
                production_plan = Production.objects.create(status=False, declared=False, branch=request.user.branch)

            dish_names = [item.get('dish') for item in items if item.get('dish')]
            dishes = Dish.objects.filter(name__in=dish_names, branch = request.user.branch)
            dish_map = {dish.name: dish for dish in dishes}

            if len(dish_map) != len(dish_names):
                return JsonResponse({'success': False, 'message': 'Some dishes do not exist'}, status=404)

            production_items = []
            production_items_update = []
            raw_materials_to_checklist = set()

            for item in items:
                portions = item.get('portions')
                dish_name = item.get('dish')
                total_cost = item.get('total_cost')

                if not portions or not dish_name:
                    return JsonResponse({'success': False, 'message': 'Missing data: portions or dish'}, status=400)

                dish = dish_map.get(dish_name)

                if dish is None:
                    return JsonResponse({'success': False, 'message': f'Dish {dish_name} does not exist'}, status=404)

                ingredients = Ingredient.objects.filter(dish=dish, minor_raw_material__branch = request.user.branch).select_related('minor_raw_material')
                if auto_confirm:
                    existing_items = ProductionItems.objects.filter(production=production_plan)
                    for existing_item in existing_items:
                        if existing_item.dish.name == dish_name:
                            production_items_update.append(ProductionItems(
                                id=existing_item.id,
                                production=production_plan,
                                portions=existing_item.portions + portions,
                                dish=dish,
                                total_cost=existing_item.total_cost + total_cost,
                                allocated=False
                            ))
                            break
                    else:
                        # Not found, create new
                        production_items.append(ProductionItems(
                            production=production_plan,
                            portions=portions,
                            dish=dish,
                            total_cost=total_cost,
                            allocated=False
                        ))
                else:
                    production_items.append(ProductionItems(
                        production=production_plan,
                        portions=portions,
                        dish=dish,
                        total_cost=total_cost,
                        allocated=False
                    ))

            if production_items:
                ProductionItems.objects.bulk_create(production_items)

            if production_items_update:
                ProductionItems.objects.bulk_update(production_items_update, ['portions', 'total_cost', 'allocated'])

            send_production_creation_notification(production_plan.id)
            logger.info(data)
            
            auto_confirm = data.get('auto', '')
            if auto_confirm:
                autoConfirmProdPlan(production_plan.id)
                
            #create e_o_d
            e_o_d, created = EndOfDay.objects.get_or_create(date=datetime.datetime.today(), branch=request.user.branch, done=False)
            
            if created:
                logger.success(f'End of day created: {e_o_d}')
                for dish in production_items:
                    EndOfDayItems.objects.create(
                        end_of_day=e_o_d,
                        dish_name=dish.dish.name,
                        total_portions=dish.portions,
                        total_sold=0,
                        staff_portions=0
                    )
            else:
                existing_items = EndOfDayItems.objects.filter(end_of_day=e_o_d).values_list('dish_name', flat=True)
                
                logger.info(f'Existing End of day')
                
                for dish in production_items:
                    if dish.dish.name not in existing_items:
                        EndOfDayItems.objects.create(
                        end_of_day=e_o_d,
                        dish_name=dish.dish.name,
                        total_portions=dish.portions,
                        total_sold=0,
                        staff_portions=0
                    )
                        
            logger.success(f'Production plan: {production_plan} successfully created.')

            return JsonResponse(
                {
                    'success': True, 
                    'message': 'Production plan created successfully', 
                    'p_plan_id': production_plan.id
                }, 
                status=201
            )
        except Exception as e:
            logger.error(f'Error creating production: {e}')
            return JsonResponse({'success': False, 'message': f'Invalid JSON data: {e}'}, status=400)


    if request.method == 'GET':
        form = ProductionPlanInlineForm()
        return render(request, 'inventory/create_production_plan.html', {'form': form})

    return JsonResponse({'success': False, 'message': 'Invalid HTTP method'}, status=405)

@login_required
def new_declare_production(request, pp_id):
    if request.method == 'GET':
        try:
            production_plan = Production.objects.select_related().get(id=pp_id, branch=request.user.branch)
            form = ProductionPlanInlineForm()
            production_plan_items = ProductionItems.objects.filter(production=production_plan)
            allocated_raw_materials = AllocatedRawMaterials.objects.filter(production=production_plan)
            
            raw_materials = []
            dish_details = []
            allocated_raw_materials = []
            total_cost = 0
            total_price = 0
            total_portions = 0

            for item in production_plan_items:
                    total_portions += item.portions
                    dish_details.append({
                            'name': item.dish.name,
                            'cost': item.dish.cost,
                            'total_price': round(item.dish.price * Decimal(item.portions), 2)
                        })
                    total_price += round(item.dish.price * Decimal(item.portions), 2)

                    for ing in Ingredient.objects.filter(dish=item.dish, minor_raw_material__branch=request.user.branch):
                        p_r_m_bf, created = ProductionRawMaterials.objects.get_or_create(
                            product=ing.minor_raw_material,
                            defaults={
                                'quantity': 0
                            })

                        quantity = round(ing.quantity * (item.portions / item.dish.portion_multiplier), 3)
                       
                        raw_material_found = next((rm for rm in raw_materials if rm['id'] == ing.minor_raw_material.id), None)
                        
                        if raw_material_found:
                            raw_material_found['quantity'] += round(float(quantity), 3)
                            raw_material_found['cost'] = round(Decimal(raw_material_found['quantity']) * ing.minor_raw_material.cost, 2)
                        else:
                            raw_materials.append({
                                'id': ing.minor_raw_material.id,
                                'name': ing.minor_raw_material.name,
                                'quantity': round(float(quantity), 3),
                                'unit': ing.minor_raw_material.unit.unit_name,
                                'cost': round(Decimal(ing.minor_raw_material.cost) * Decimal(quantity), 2),
                            })
                        
                        raw_material_prod = Product.objects.get(id = ing.minor_raw_material.id)
                        raw_material_prod_found = next((rm for rm in allocated_raw_materials if rm['id'] == raw_material_prod.id), None)

                        if raw_material_prod_found:
                            pass
                        else:
                            allocated_raw_materials.append(
                                {
                                    'id': raw_material_prod.id,
                                    'name': raw_material_prod.name,
                                    'quantity': round(float(raw_material_prod.quantity), 3),
                                    'unit': raw_material_prod.unit.unit_name,
                                    'cost': round(Decimal(raw_material_prod.cost) * Decimal(raw_material_prod.quantity), 2),
                                }
                            )
      
            allocated_raw_material_total_cost = 0
            allocated_raw_material_total_qnty = 0
            
            for items in allocated_raw_materials:
                allocated_raw_material_total_cost += items['cost']
                allocated_raw_material_total_qnty += items['quantity']

            for cost in raw_materials:
                total_cost += cost['cost']

        except Production.DoesNotExist:
            messages.warning(request, f'Production Plan With ID: {pp_id} doesn\'t exist.')
            return redirect('inventory:production_plan_detail', pp_id)
        
        return render(request, 'inventory/new_declare.html', {
            'p_plan': production_plan,
            'production_plan': production_plan_items,
            'ingridients':raw_materials,
            'allocated': allocated_raw_materials,
            'production_plan_id': pp_id,
            'total_price': dish_details,
            'total': total_cost,
            'total_portions': total_portions,
            'price': total_price,
            'form': form,
            'all_r_m_cost':allocated_raw_material_total_cost,
            'all_r_m_qnty':allocated_raw_material_total_qnty,
        })
        
    if request.method == 'POST':
        data = json.loads(request.body)

        dish_name = data.get('dish_name').split('@')[0].strip()
        portions = data.get('portions')

        try:
            dish_ing = Ingredient.objects.filter(dish__name = dish_name, minor_raw_material__branch=request.user.branch)
            
            ingridient_list = []
            for ingridient in dish_ing:
                portion_m = ingridient.dish.portion_multiplier
                qnty = ingridient.quantity

                prop = qnty/portion_m
                declared_total_qnty = prop * int(portions)
                ingridient_list.append({
                    'ingridient_name': ingridient.minor_raw_material.name,
                    'ingridient_qnty': round(declared_total_qnty, 3)
                })
                
            with transaction.atomic():
                production = Production.objects.get(id=pp_id, branch=request.user.branch)
                production_item = ProductionItems.objects.get(production=production, dish__name=dish_name)
                production_item.declared_quantity = float(portions)
                production_item.save()
                
                eod, created = EndOfDay.objects.get_or_create(date=datetime.datetime.now(), branch=request.user.branch, done=False)
                
                if eod:
                    logger.info(f'EndOfDay already exists for date: {eod.date}')
                    eod_item = EndOfDayItems.objects.filter(end_of_day=eod, dish_name=dish_name).first()
                    eod_item.declared = float(portions)
                    eod_item.expected = production_item.portions
                    eod_item.save()
                
                logger.success(f'Successfully updated EOD item for dish: {dish_name} with declared portions: {portions}')
                return JsonResponse({'success':True, 'ingridient': ingridient_list}, status = 200)
        except Exception as e:
            logger.error(f'Error: {e}')
            return JsonResponse({'success': False}, status= 400)
        
    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
            ing_data = data.get('data', '')
            dish_data = data.get('data_dish', '')
            
            logger.info({
                'ING': ing_data,
                'DISH': dish_data
            })

            try:
                production= Production.objects.get(id=pp_id, branch=request.user.branch)
            except ProductionItems.DoesNotExist:
                return JsonResponse({'success': False, 'message': f'Production Plan with ID: {pp_id} doesn\'t exist'}, status=404)

            edit_pplan_portions = []

            for ing in ing_data:
                logger.info({
                    'name': ing.get('ingridient_name'),
                    'used_qnty': ing.get('system'),
                    'variance': ing.get('variance')
                })
            
                # try:
                #     allocated = AllocatedRawMaterials.objects.get(raw_material__name=ing.get('ingridient_name'), production=production)
                # except ProductionItems.DoesNotExist:
                #     return JsonResponse({'success': False, 'message': f'Raw Material with ID: {ing.get('ingridient_name')} doesn\'t exist'}, status=404)

                try:
                    product = Product.objects.get(name=ing.get('ingridient_name'), branch=request.user.branch)
                    p_rm_variance = ProductionVariance.objects.create(
                        production=production,
                        ingredient=product,
                        quantity=float(ing.get('variance'))
                    )
                    logger.info(p_rm_variance)
                except ProductionVariance.DoesNotExist:
                    return JsonResponse({'success': False, 'message': f'Variance for Raw Material with ID: {ing.get('ingridient_name')} doesn\'t exist'}, status=404)
                
                with transaction.atomic():
                    p_rm = ProductionRawMaterials.objects.get(product__name=ing.get('ingridient_name'))
                    p_rm.quantity -= float(ing.get('system'))
                    
                    
                    # allocated.remaining_quantity = allocated.quantity - float(ing.get('system'))
                    # allocated.save()
                    
                    ProductionLogs.objects.create(
                        user=request.user, 
                        action= 'declared',
                        description='from warehouse',
                        product=p_rm,
                        quantity=p_rm.quantity,
                        total_quantity=p_rm.quantity,
                    )
                    p_rm.save()
    
            try:
                production = Production.objects.get(id=pp_id, branch=request.user.branch)  
                production_plan_items = ProductionItems.objects.filter(production=production)
                total_cost = production_plan_items.aggregate(total_cost=Sum('total_cost'))['total_cost'] or 0
            except Production.DoesNotExist:
                return JsonResponse({'success':False, 'message':f'Production with ID: {pp_id}, doesn\'t exists'})
      
            declaration_flag = True
            with transaction.atomic():
                COGS.objects.create(
                    production=production,
                    amount=total_cost,
                    # branch=request.user.branch
                )
                
                if declaration_flag:
                    
                    production.declared = True
                    production.save()
            
            for dish in dish_data:
                logger.info({
                    'name': dish.get('dish_name'),
                    'p_portions': dish.get('planned_portions'),
                    'declared': dish.get('declared'),
                    'note': dish.get('note', '')
                })
                if dish.get('note'):
                    note = dish.get('note', '')
                    extra_portions = Decimal(note.split(':')[1].strip())
                    edit_pplan_portions.append(
                        {
                            'name': dish.get('dish_name'),
                            'portions': dish.get('declared'),
                            'planned_portions': dish.get('planned_portions'),
                            'add_portions': extra_portions
                        }
                    )

            logger.info(edit_pplan_portions)
            if edit_pplan_portions:
                editProdPlan(prod_id=pp_id, data=edit_pplan_portions)

            return JsonResponse({'success': True})
        except Exception as e:
            logger.error(f'Error: {e}')
            return JsonResponse({'success':False})
        
@login_required
def update_ingredient_actuals(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            ingredient_id = data.get('ingredient_id')
            production_id = data.get('production_id')

            ngredient = Ingredient.objects.get(id=ingredient_id)
            actual_quantity = float(data.get("actual_quantity"))
            actual_cost = float(data.get("actual_cost"))
            variance_cost = float(data.get("variance_cost"))
            variance_units = float(data.get("variance_units"))
            system_cost = float(data.get("system_cost"))

            prod_ing = get_object_or_404(ProductionIngriedients, id=data.get("id"))

            prod_ing, _ = ProductionIngriedients.objects.get_or_create(
                production_id=production_id
            )

            prod_ing.actual_quantity = actual_quantity
            prod_ing.total_cost = system_cost 
            prod_ing.variance_cost =  variance_cost
            prod_ing.variance_unit = variance
            prod_ing.ingredient = ngredient
            prod_ing.save()

            return JsonResponse({"status": "success"})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=400)

    return JsonResponse({"status": "invalid method"}, status=405)


