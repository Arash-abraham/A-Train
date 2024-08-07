from colorama import *
import sys , os , time
import re

def Banner():
    time.sleep(0.1)
    os.system('clear')
    time.sleep(0.5)
    print(Fore.BLUE+"""
 █████╗       ████████╗██████╗  █████╗ ██╗███╗   ██╗
██╔══██╗      ╚══██╔══╝██╔══██╗██╔══██╗██║████╗  ██║
███████║█████╗   ██║   ██████╔╝███████║██║██╔██╗ ██║
██╔══██║╚════╝   ██║   ██╔══██╗██╔══██║██║██║╚██╗██║
██║  ██║         ██║   ██║  ██║██║  ██║██║██║ ╚████║
╚═╝  ╚═╝         ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝       
    """+Style.RESET_ALL)

def Checker_function():
    while True: 
        try:
            Banner()
            regex = input(Fore.WHITE + 'Do you want to apply a regex pattern to filter the results' + Fore.LIGHTWHITE_EX + ' (' + Fore.LIGHTBLUE_EX + 'Y ' + Fore.LIGHTWHITE_EX + '/' + Fore.LIGHTBLUE_EX + ' N' + Fore.LIGHTWHITE_EX + ')' + Fore.BLUE + ' ? ' + Fore.WHITE + '').upper()
            if regex == 'Y':
                With_Regex()
                break
            elif regex == 'N':
                No_Regex()
                break
            else:
                Banner()
                time.sleep(0.5)
                print(Fore.WHITE + '\n\nWrong value, enter the value with' + Fore.LIGHTWHITE_EX + ' (' + Fore.LIGHTBLUE_EX + 'Y ' + Fore.LIGHTWHITE_EX + '/' + Fore.LIGHTBLUE_EX + ' N' + Fore.LIGHTWHITE_EX + ')')
                time.sleep(0.5)
                input(Fore.WHITE + 'Press Enter to try again ...')  
        except KeyboardInterrupt:
            time.sleep(0.1)
            print(Fore.BLUE+'\n\nOk By')
            exit()

def With_Regex():
    while True:
        try:
            Banner()
            time.sleep(0.5)
            input1 = input(Fore.WHITE + 'Enter name of the first file (the values of the second file will be searched on this file)' + Fore.BLUE + ' => ' + Fore.WHITE + '')
            with open(input1, 'r') as file1:
                input_data_1 = set(file1.read().splitlines())
            break
        except FileNotFoundError:
            Banner()
            time.sleep(0.5)
            print(Fore.BLUE + '\n\nNo such file or directory, Try again')
            input(Fore.WHITE + 'Press Enter to try again ...')
    while True:
        try:
            Banner()
            time.sleep(0.5)
            input2 = input(Fore.WHITE + 'Enter name of the second file whose values you want to search in the first file' + Fore.BLUE + ' => ' + Fore.WHITE + '')
            with open(input2, 'r') as file2:
                input_data_2 = set(file2.read().splitlines())
            break
        except FileNotFoundError:
            Banner()
            time.sleep(0.5)
            print(Fore.WHITE + '\n\nNo such file or directory, Try again')
            input(Fore.WHITE + 'Press Enter to try again ...')

    while True:
        try:
            Banner()
            time.sleep(0.5)
            regex_pattern = input(Fore.WHITE + 'Enter regex pattern to filter results (leave empty to skip filtering)' + Fore.BLUE + ' => ' + Fore.WHITE + '')

            compiled_pattern = re.compile(regex_pattern)

            output_data = [
                data for data in input_data_2 
                if data not in input_data_1 and (compiled_pattern is None or not compiled_pattern.match(data))
            ]

            Banner()
            if output_data:
                for data in output_data:
                    print(Fore.LIGHTBLUE_EX + data)
            else:
                print(Fore.WHITE + "No matching values found to print.")
            break
        except re.error:
            Banner()
            print(Fore.WHITE + 'Invalid regex pattern. Please try again.') 
            time.sleep(0.5)
            input(Fore.WHITE + 'Press Enter to try again ...')    

    # except KeyboardInterrupt:
    #     print(Fore.BLUE + '\n\nOk By')


def No_Regex():
    try:
        Banner()
        try:
            time.sleep(0.5)
            input1 = input(Fore.WHITE+'Enter name of the first file (the values ​​of the second file will be searched on this file)'+Fore.BLUE+' => '+Fore.WHITE+'')
            with open(input1, 'r') as file1:
                input_data_1 = set(file1.read().split())
        except FileNotFoundError:
            time.sleep(0.5)
            print(Fore.BLUE+'\n\nNo such file or directory , Try again')
            exit()
        Banner()
        try:
            time.sleep(0.5)
            input2 = input(Fore.WHITE+'Enter name of the second file whose values ​​you want to search in the first file'+Fore.BLUE+' => '+Fore.WHITE+'')
            with open(input2, 'r') as file2:
                input_data_2 = set(file2.read().split())
        except FileNotFoundError:
            time.sleep(0.5)
            print(Fore.BLUE+'\n\nNo such file or directory , Try again')
            exit()
        missing_data = input_data_2 - input_data_1
        Banner()
        for data in missing_data:
            time.sleep(0.1)
            print(Fore.LIGHTBLUE_EX+data)
    except KeyboardInterrupt:
        print(Fore.BLUE+'\n\nOk By')
    except FileNotFoundError:
        print(Fore.BLUE+'\n\nNo such file or directory , Try again')

if __name__ == '__main__' :
    Checker_function()