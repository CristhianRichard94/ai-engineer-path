



import os
import shutil
import git


def download_repo(input_url):
    if os.path.exists("temp"):
        shutil.rmtree('temp', ignore_errors=True)
        os.system("rmdir /s /q temp")
    git.Repo.clone_from(input_url, 'temp'+ os.sep + os.path.basename(input_url))
