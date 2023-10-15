

async def driver_data_state_to_data_core(driver_data_state: dict):
    return {
        'car':{
            'color' : driver_data_state.get('car_color'),
            'brand' : {
                'name' : driver_data_state.get('car_brand')
            },
            'number' : driver_data_state.get('car_number'),
            
        },
        'phone_number' : driver_data_state.get('phone_number'),
        'baby_chair' : True if driver_data_state.get('baby_chair') == 'Да' else False,
    }
    